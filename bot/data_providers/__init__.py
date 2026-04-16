from .base import DataProvider
from .mt5_provider import MT5Provider
from .oanda_provider import OandaProvider


def create_provider(config) -> DataProvider:
    """Factory: create the right data provider based on config."""
    if config.data_provider == "mt5":
        return MT5Provider(
            login=config.mt5_login,
            password=config.mt5_password,
            server=config.mt5_server,
            timezone=config.timezone,
        )
    elif config.data_provider == "oanda":
        return OandaProvider(
            api_token=config.oanda_api_token,
            account_id=config.oanda_account_id,
            environment=config.oanda_environment,
            timezone=config.timezone,
        )
    else:
        raise ValueError(f"Unknown data provider: {config.data_provider}")
