#!/usr/bin/env python3
"""Probe for LR5 endpoints using authenticated credentials."""

import asyncio
from credentials_helper import get_credentials
from pylitterbot import Account

async def probe_lr5():
    """Try to find LR5 API endpoints."""
    username, password = get_credentials()
    
    # Connect to get auth token
    account = Account()
    await account.connect(username=username, password=password, load_robots=True)
    
    print("\n=== Robots Found ===")
    for robot in account.robots:
        print(f"  {robot.name}: {robot.model} (Serial: {robot.serial})")
        print(f"    Type: {type(robot).__name__}")
        
    # Check if any are LR5
    lr5_robots = [r for r in account.robots if 'LitterRobot5' in type(r).__name__ or '5' in r.model]
    
    if lr5_robots:
        print("\n🎉 FOUND LR5 ROBOT(S)!")
        for robot in lr5_robots:
            print(f"\nLR5 Robot: {robot.name}")
            print(f"  Model: {robot.model}")
            print(f"  Serial: {robot.serial}")
            # Try to get activity data
            try:
                if hasattr(robot, 'get_activity'):
                    activity = await robot.get_activity()
                    print(f"  Activity data: {activity}")
            except Exception as e:
                print(f"  Activity error: {e}")
    else:
        print("\n❌ No LR5 robots found in account")
        print("    LR5 support not yet implemented in pylitterbot")
    
    # Check the auth token and API base URLs being used
    print("\n=== API Configuration ===")
    if hasattr(account, '_session'):
        print(f"  Session: {account._session}")
    if hasattr(account, 'user_id'):
        print(f"  User ID: {account.user_id}")
        
    await account.disconnect()

if __name__ == '__main__':
    asyncio.run(probe_lr5())
