import asyncio

from pylitterbot import Account

# Set email and password for initial authentication.
username = "Your username"
password = "Your password"


async def main():
    # Create an account.
    account = Account()
    # Connect to the API and load robots
    await account.connect(username=username, password=password, load_robots=True)

    # Print robots associated with account.
    print("Robots:")
    for robot in account.robots:
        print(robot)


if __name__ == "__main__":
    asyncio.run(main())
