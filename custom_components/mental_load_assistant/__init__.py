"""The Mental load Assistant integration."""
DOMAIN = "mental_load"

def setup(hass, config):
    hass.states.async_set("mental_load.world", "Sduniii")

    # Return boolean to indicate that initialization was successful.
    return True