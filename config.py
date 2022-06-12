from typing import Dict, Optional
from dotenv import dotenv_values
from entities import ConfigurationEntity


class ConfigurationMapper:
    def __init__(self, env: str) -> None:

        env = env.lower()

        __config_raw: Dict[str, Optional[str]] = dotenv_values(".env.{}".format(env))

        self.config = ConfigurationEntity(
            gitlab_username=str(__config_raw.get("gitlab_username")),
            gitlab_token=str(__config_raw.get("gitlab_token")),
            gitlab_url=str(__config_raw.get("gitlab_url")),
            influx_url=str(__config_raw.get("influx_url")),
            influx_token=str(__config_raw.get("influx_token")),
            influx_org=str(__config_raw.get("influx_org"))
        )
