#!/usr/bin/env python3
"""Deep introspection of LR4 GraphQL schema."""

import asyncio
import sys
import json


async def main():
    from pylitterbot.session import LitterRobotSession
    from credentials_helper import get_credentials

    # Try to get credentials from args or file
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        print("Using credentials from command line")
    else:
        username, password = get_credentials()
        if not username or not password:
            print("\nNo credentials found. Run: python credentials_helper.py")
            print("Or provide: python introspect_schema.py <email> <password>")
            return
        print("Using credentials from .whisker_credentials")

    session = LitterRobotSession()
    await session.login(username=username, password=password)

    # Full introspection query
    introspection = {
        "query": """
            query IntrospectionQuery {
                __schema {
                    queryType {
                        name
                        fields {
                            name
                            description
                            args {
                                name
                                description
                                type {
                                    name
                                    kind
                                    ofType {
                                        name
                                        kind
                                    }
                                }
                            }
                            type {
                                name
                                kind
                                fields {
                                    name
                                    description
                                    type {
                                        name
                                        kind
                                        ofType {
                                            name
                                            kind
                                        }
                                    }
                                }
                            }
                        }
                    }
                    types {
                        name
                        kind
                        description
                        fields {
                            name
                            description
                            type {
                                name
                                kind
                                ofType {
                                    name
                                    kind
                                }
                            }
                        }
                    }
                }
            }
        """
    }

    print("=" * 60)
    print("Introspecting LR4 GraphQL Schema")
    print("=" * 60)

    response = await session.post(
        "https://lr4.iothings.site/graphql",
        json=introspection
    )

    schema = response.get("data", {}).get("__schema", {})

    # Find the robot query
    print("\n--- 'robot' Query Details ---")
    query_type = schema.get("queryType", {})
    for field in query_type.get("fields", []):
        if field["name"] == "robot":
            print(f"Name: {field['name']}")
            print(f"Description: {field.get('description', 'N/A')}")
            print(f"Return Type: {field['type']['name']}")
            print(f"Arguments:")
            for arg in field.get("args", []):
                arg_type = arg["type"]
                type_str = arg_type.get("name") or arg_type.get("ofType", {}).get("name")
                print(f"  - {arg['name']}: {type_str} ({arg.get('description', 'N/A')})")

    # Find RobotData type
    print("\n--- 'RobotData' Type Details ---")
    for type_def in schema.get("types", []):
        if type_def["name"] == "RobotData":
            print(f"Description: {type_def.get('description', 'N/A')}")
            print(f"Fields:")
            for field in type_def.get("fields", []) or []:
                field_type = field["type"]
                type_str = field_type.get("name") or field_type.get("ofType", {}).get("name")
                print(f"  - {field['name']}: {type_str} ({field.get('description', 'N/A')})")

    # Look for any LR5 related types
    print("\n--- Types containing 'lr5', 'litterrobot5', or 'v5' ---")
    for type_def in schema.get("types", []):
        name = type_def["name"].lower()
        if any(x in name for x in ["lr5", "litterrobot5", "robot5", "v5"]):
            print(f"{type_def['name']}: {type_def.get('description', 'N/A')}")

    # Check if there are any mutation types for LR5
    print("\n--- All Query Types (looking for LR5 patterns) ---")
    for field in query_type.get("fields", []):
        name = field["name"].lower()
        if "robot" in name or "lr" in name or "litter" in name:
            args_str = ", ".join(f"{a['name']}: {a['type'].get('name') or a['type'].get('ofType', {}).get('name')}"
                               for a in field.get("args", []))
            print(f"{field['name']}({args_str}): {field['type']['name']}")

    # Save full schema to file for reference
    with open("lr4_schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("\n✓ Full schema saved to lr4_schema.json")

    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
