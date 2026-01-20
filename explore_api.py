#!/usr/bin/env python3
"""Explore Whisker API to see what data is available for LR5."""

import asyncio
import getpass
import json
from datetime import datetime


async def main():
    import sys
    # Import here so we can catch import errors
    from pylitterbot import Account
    from credentials_helper import get_credentials

    print("=" * 60)
    print("Whisker API Explorer")
    print("=" * 60)

    # Get credentials from args or file
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username, password = get_credentials()
        if not username or not password:
            username = input("Whisker account email: ")
            password = getpass.getpass("Whisker account password: ")

    print("\nConnecting to Whisker API...")

    account = Account()
    try:
        await account.connect(
            username=username,
            password=password,
            load_robots=True,
            load_pets=True,
        )
        print("Connected successfully!\n")

        # Display user info
        print("=" * 60)
        print("USER INFO")
        print("=" * 60)
        print(f"User ID: {account.user_id}")

        # Display all robots
        print("\n" + "=" * 60)
        print("ROBOTS")
        print("=" * 60)

        if not account.robots:
            print("No robots found!")
        else:
            for i, robot in enumerate(account.robots, 1):
                print(f"\n--- Robot {i} ---")
                print(f"Type: {type(robot).__name__}")
                print(f"Name: {robot.name}")
                print(f"Serial: {robot.serial}")
                print(f"Model: {getattr(robot, 'model', 'Unknown')}")
                print(f"ID: {robot.id}")

                # Dump all available attributes
                print("\nAll properties:")
                for attr in sorted(dir(robot)):
                    if not attr.startswith("_") and not callable(getattr(robot, attr, None)):
                        try:
                            val = getattr(robot, attr)
                            if val is not None:
                                print(f"  {attr}: {val}")
                        except Exception as e:
                            print(f"  {attr}: <error: {e}>")

                # Check raw data
                if hasattr(robot, "_data"):
                    print("\nRaw API data:")
                    print(json.dumps(robot._data, indent=2, default=str))

        # Display all pets
        print("\n" + "=" * 60)
        print("PETS")
        print("=" * 60)

        if not account.pets:
            print("No pets found!")
        else:
            for i, pet in enumerate(account.pets, 1):
                print(f"\n--- Pet {i} ---")
                print(f"Name: {pet.name}")
                print(f"ID: {pet.id}")
                print(f"Type: {pet.pet_type}")
                print(f"Gender: {pet.gender}")
                print(f"Weight: {pet.weight} lbs")
                print(f"Last Weight Reading: {pet.last_weight_reading}")
                print(f"Estimated Weight: {pet.estimated_weight}")
                print(f"Weight ID Feature Enabled: {pet.weight_id_feature_enabled}")

                # Fetch weight history
                print("\nFetching weight history...")
                try:
                    weight_history = await pet.fetch_weight_history(limit=10)
                    if weight_history:
                        print(f"Last {len(weight_history)} weight readings:")
                        for w in weight_history[:10]:
                            print(f"  {w.timestamp}: {w.weight} lbs")
                    else:
                        print("  No weight history available")
                except Exception as e:
                    print(f"  Error fetching weight history: {e}")

                # Raw pet data
                if hasattr(pet, "_data"):
                    print("\nRaw pet data:")
                    print(json.dumps(pet._data, indent=2, default=str))

        # Try to get activity history if available
        print("\n" + "=" * 60)
        print("ACTIVITY HISTORY (last 10 entries)")
        print("=" * 60)

        for robot in account.robots:
            if hasattr(robot, "get_activity_history"):
                print(f"\n--- {robot.name} ---")
                try:
                    activities = await robot.get_activity_history(limit=10)
                    for activity in activities:
                        print(f"  {activity}")
                except Exception as e:
                    print(f"  Error: {e}")

        # Try to get insights
        print("\n" + "=" * 60)
        print("INSIGHTS")
        print("=" * 60)

        for robot in account.robots:
            if hasattr(robot, "get_insight"):
                print(f"\n--- {robot.name} ---")
                try:
                    insight = await robot.get_insight(days=7)
                    print(f"  {insight}")
                except Exception as e:
                    print(f"  Error: {e}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await account.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(main())
