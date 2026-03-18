"""Config flow for Ista Norway."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .api import (
    IstaAuthError,
    IstaClient,
    IstaConnectionError,
    IstaResponseError,
    IstaTwoFactorError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class IstaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ista Norway."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — username & password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            # Prevent duplicate entries
            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()

            # Validate credentials
            client = IstaClient(username, password)
            try:
                await client.authenticate()
            except IstaAuthError:
                errors["base"] = "invalid_auth"
            except IstaTwoFactorError:
                errors["base"] = "two_factor_required"
            except (IstaConnectionError, IstaResponseError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                return self.async_create_entry(
                    title=f"Ista Norway ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
