#!/usr/bin/env python3
"""Probe for LR5 API endpoints."""

import asyncio
import getpass
import json
from typing import Any


async def main():
    import sys
    from pylitterbot.session import LitterRobotSession

    print("=" * 60)
    print("LR5 API Endpoint Probe")
    print("=" * 60)

    # Accept credentials from command line args or prompt
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        print(f"Using credentials from command line arguments")
    else:
        username = input("Whisker account email: ")
        password = getpass.getpass("Whisker account password: ")

    session = LitterRobotSession()
    await session.login(username=username, password=password)

    user_id = session.get_user_id()
    print(f"\nUser ID: {user_id}")
    print(f"Token type: {type(session.tokens)}")

    # Get authorization header
    auth_header = await session.get_bearer_authorization()
    print(f"Auth header obtained: {bool(auth_header)}")

    # Potential LR5 endpoints to probe based on patterns
    endpoints_to_try = [
        # REST-style endpoints (LR5 reportedly uses REST)
        ("GET", "https://lr5.iothings.site/api/users/{user_id}/robots", "LR5 REST - users robots"),
        ("GET", "https://lr5.iothings.site/api/robots", "LR5 REST - robots"),
        ("GET", "https://lr5.iothings.site/users/{user_id}/robots", "LR5 REST alt - users robots"),
        ("GET", "https://api.whisker.iothings.site/users/{user_id}/robots", "Whisker API - users"),
        ("GET", "https://platform.api.whisker.iothings.site/users/{user_id}/litter-robots", "Platform API"),

        # GraphQL endpoints
        ("POST", "https://lr5.iothings.site/graphql", "LR5 GraphQL"),
        ("POST", "https://api.lr5.iothings.site/graphql", "LR5 API GraphQL"),

        # Try the LR4 endpoint to see what it returns for all robots
        ("POST", "https://lr4.iothings.site/graphql", "LR4 GraphQL - all robots query"),
    ]

    # Standard GraphQL query for robots
    graphql_query = {
        "query": """
            query GetRobots($userId: String!) {
                getLitterRobotsByUser(userId: $userId) {
                    unitId
                    name
                    serial
                    model
                }
            }
        """,
        "variables": {"userId": user_id},
    }

    # LR4-style query
    lr4_query = {
        "query": """
            query GetLR4($userId: String!) {
                getLitterRobot4ByUser(userId: $userId) {
                    unitId
                    name
                    serial
                }
            }
        """,
        "variables": {"userId": user_id},
    }

    # Try a generic "all robots" query
    all_robots_query = {
        "query": """
            query {
                __schema {
                    queryType {
                        fields {
                            name
                            description
                        }
                    }
                }
            }
        """
    }

    print("\n" + "=" * 60)
    print("Probing endpoints...")
    print("=" * 60)

    for method, endpoint_template, description in endpoints_to_try:
        endpoint = endpoint_template.format(user_id=user_id)
        print(f"\n--- {description} ---")
        print(f"  {method} {endpoint}")

        try:
            if method == "GET":
                response = await session.get(endpoint)
            else:  # POST
                if "lr4" in endpoint:
                    response = await session.post(endpoint, json=lr4_query)
                else:
                    response = await session.post(endpoint, json=graphql_query)

            print(f"  Status: SUCCESS")
            if response:
                if isinstance(response, dict):
                    print(f"  Response: {json.dumps(response, indent=4, default=str)[:500]}...")
                else:
                    print(f"  Response: {str(response)[:500]}...")
        except Exception as e:
            error_str = str(e)
            if "404" in error_str:
                print(f"  Status: 404 Not Found")
            elif "401" in error_str:
                print(f"  Status: 401 Unauthorized")
            elif "403" in error_str:
                print(f"  Status: 403 Forbidden")
            else:
                print(f"  Status: Error - {error_str[:100]}")

    # Try to introspect LR4 schema
    print("\n" + "=" * 60)
    print("Introspecting LR4 GraphQL Schema...")
    print("=" * 60)

    try:
        response = await session.post(
            "https://lr4.iothings.site/graphql",
            json=all_robots_query
        )
        if response and "data" in response:
            fields = response.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
            print("\nAvailable queries:")
            for field in fields:
                name = field.get("name", "")
                desc = field.get("description", "")
                # Look for anything robot-related
                if any(x in name.lower() for x in ["robot", "litter", "lr"]):
                    print(f"  - {name}: {desc}")
    except Exception as e:
        print(f"Schema introspection failed: {e}")

    # Check pet-profile endpoint for any robot associations
    print("\n" + "=" * 60)
    print("Checking Pet Profile API for robot associations...")
    print("=" * 60)

    pet_query = {
        "query": """
            query GetPetsByUser($userId: String!) {
                getPetsByUser(userId: $userId) {
                    petId
                    name
                    whiskerProducts
                    petTagAssigned {
                        petTag {
                            petTagId
                        }
                    }
                }
            }
        """,
        "variables": {"userId": user_id},
    }

    try:
        response = await session.post(
            "https://pet-profile.iothings.site/graphql/",
            json=pet_query
        )
        if response:
            print(json.dumps(response, indent=2, default=str))
    except Exception as e:
        print(f"Pet profile query failed: {e}")

    await session.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
