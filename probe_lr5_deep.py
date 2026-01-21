#!/usr/bin/env python3
"""Deep probe for LR5 API endpoints based on known patterns."""

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
    else:
        username, password = get_credentials()
        if not username or not password:
            print("No credentials found. Run: python credentials_helper.py")
            return

    session = LitterRobotSession()
    await session.login(username=username, password=password)

    user_id = session.get_user_id()
    print(f"User ID: {user_id}\n")

    # Based on existing patterns, try variations
    base_domains = [
        "iothings.site",
        "whisker.iothings.site",
        "api.whisker.com",
        "whisker.com",
    ]

    prefixes = ["lr5", "litterrobot5", "litter-robot-5", "v3", "v4", "v5"]
    paths = [
        f"/users/{user_id}/robots",
        f"/api/users/{user_id}/robots",
        f"/api/v1/users/{user_id}/robots",
        f"/api/v2/users/{user_id}/robots",
        "/api/robots",
        "/robots",
        f"/user/{user_id}/devices",
    ]

    # Try REST endpoints
    print("=" * 60)
    print("Trying REST endpoint variations...")
    print("=" * 60)

    tested_urls = set()

    for domain in base_domains:
        for prefix in prefixes:
            for path in paths:
                url = f"https://{prefix}.{domain}{path}"

                if url in tested_urls:
                    continue
                tested_urls.add(url)

                try:
                    response = await session.get(url)
                    print(f"✓ SUCCESS: {url}")
                    print(f"  Response: {json.dumps(response, indent=2, default=str)[:300]}")
                    print()
                except Exception as e:
                    error_msg = str(e)
                    if "Name or service not known" not in error_msg and "Cannot connect" not in error_msg:
                        print(f"⚠ {url}")
                        print(f"  Error: {error_msg[:100]}")

    # Try the generic 'robot' query from LR4 schema
    print("\n" + "=" * 60)
    print("Trying generic 'robot' query on LR4 endpoint...")
    print("=" * 60)

    queries = [
        {
            "query": """
                query {
                    robot {
                        unitId
                        name
                        serial
                    }
                }
            """
        },
        {
            "query": f"""
                query {{
                    robot(userId: "{user_id}") {{
                        unitId
                        name
                        serial
                    }}
                }}
            """
        },
        {
            "query": f"""
                query GetRobot($userId: String!) {{
                    robot(userId: $userId) {{
                        unitId
                        name
                        serial
                    }}
                }}
            """,
            "variables": {"userId": user_id},
        },
    ]

    for i, query in enumerate(queries, 1):
        try:
            response = await session.post("https://lr4.iothings.site/graphql", json=query)
            print(f"\nQuery {i}: {query.get('query', '')[:100]}...")
            print(f"Response: {json.dumps(response, indent=2, default=str)}")
        except Exception as e:
            print(f"Query {i} failed: {e}")

    # Check if there's a household or device management endpoint
    print("\n" + "=" * 60)
    print("Checking for household/device management endpoints...")
    print("=" * 60)

    household_endpoints = [
        f"https://v2.api.whisker.iothings.site/households/{user_id}",
        f"https://v2.api.whisker.iothings.site/users/{user_id}/households",
        f"https://graphql.whisker.iothings.site/v1/graphql",  # Feeder uses this
    ]

    for url in household_endpoints:
        try:
            response = await session.get(url)
            print(f"✓ {url}")
            print(f"  Response: {json.dumps(response, indent=2, default=str)[:500]}")
        except Exception as e:
            if "404" not in str(e) and "Cannot connect" not in str(e):
                print(f"⚠ {url}: {str(e)[:100]}")

    # Try GraphQL introspection on feeder endpoint to see if it knows about LR5
    print("\n" + "=" * 60)
    print("Introspecting Feeder GraphQL for LR5 types...")
    print("=" * 60)

    introspection = {
        "query": """
            query {
                __schema {
                    types {
                        name
                        description
                    }
                }
            }
        """
    }

    try:
        response = await session.post(
            "https://graphql.whisker.iothings.site/v1/graphql",
            json=introspection
        )
        types = response.get("data", {}).get("__schema", {}).get("types", [])
        print("\nTypes containing 'litter' or 'robot':")
        for t in types:
            name = t.get("name", "")
            if any(x in name.lower() for x in ["litter", "robot", "lr", "whisker"]):
                print(f"  - {name}: {t.get('description', 'N/A')}")
    except Exception as e:
        print(f"Introspection failed: {e}")

    await session.close()
    print("\n" + "=" * 60)
    print("Probe complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
