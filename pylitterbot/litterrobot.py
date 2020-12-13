from dataclasses import dataclass


@dataclass(init=False, frozen=True)
class Vendor:
    name: str
    endpoint: str
    token_endpoint: str
    client_id: str
    client_secret: str
    x_api_key: str


class LitterRobot(Vendor):
    name = "Litter-Robot"
    endpoint = "https://v2.api.whisker.iothings.site"
    token_endpoint = "https://autopets.sso.iothings.site/oauth/token"
    client_id = "IYXzWN908psOm7sNpe4G.ios.whisker.robots"
    client_secret = "C63CLXOmwNaqLTB2xXo6QIWGwwBamcPuaul"
    x_api_key = "p7ndMoj61npRZP5CVz9v4Uj0bG769xy6758QRBPb"
