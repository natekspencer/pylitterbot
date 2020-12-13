from pylitterbot import Account

# Set email and password for initial authentication.
username = "Your username"
password = "Your password"

# Create an account with credentials.
account = Account(username=username, password=password)

# Print robots associated with account.
print("Robots:")
for robot in account.robots:
    print(robot)
