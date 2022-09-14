import socket

from .effects import MONO_EFFECTS, PRESET_EFFECTS
from .constants import (Command, CommandFlag, MonoEffect)
from .utils import clamp
from .WifiLedShopLightState import WifiLedShopLightState
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_WHITE,
    EFFECT_COLORLOOP,
    EFFECT_RANDOM,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_EFFECT,
    SUPPORT_WHITE_VALUE,
    LightEntity,
)
import homeassistant.util.color as color_util

class WifiLedShopLight(LightEntity):
  """
  A Wifi LED Shop Light
  """

  def __init__(self, ip, name, port = 8189, timeout = 1, retries = 5):
    """
    Creates a new Wifi LED Shop light

    :param ip: The IP of the controller on the network (STA Mode, not AP mode).
    :param port: The port the controller should listen on. It should almost always be left as the default.
    :param timeout: The timeout in seconds to wait listening to the socket.
    :param retries: The number of times to retry sending a command if it fails or times out before giving up.
    """
    self._name = name
    self._ip = ip
    self._port = port
    self._timeout = timeout
    self._retries = retries
    self._state = WifiLedShopLightState()
    self._sock = None
    self._unique_id = self.send_command(Command.GET_ID, []).decode('utf-8')
    self.update()

  def __enter__(self):
    return self

  def __exit__(self, type, value, traceback):
    self._sock.close()

  def set_color(self, r=0, g=0, b=0):
    """
    Sets the color of the light (rgb each 0 to 255)
    """
    r = clamp(r)
    g = clamp(g)
    b = clamp(b)
    self._state.color = (r, g, b)
    self.send_command(Command.SET_COLOR, [int(r), int(g), int(b)])

  def set_brightness(self, brightness=0):
    """
    Sets the brightness of the light

    :param brightness: An int describing the brightness (0 to 255, where 255 is the brightest)
    """
    brightness = clamp(brightness)
    self._state.brightness = brightness
    self.send_command(Command.SET_BRIGHTNESS, [int(brightness)])

  def set_white(self, white=0):
    """
    Sets the white brightness of the light

    :param white: An int describing the white brightness (0 to 255, where 255 is the brightest)
    """
    white = clamp(white)
    self._state.white = white
    self.send_command(Command.SET_WHITE, [int(white)])

  def set_speed(self, speed=0):
    """
    Sets the speed of the effect. Not all effects use the speed, but it can be safely set regardless

    :param speed: An int describing the speed an effect will play at. (0 to 255, where 255 is the fastest)
    """
    speed = clamp(speed)
    self._state.speed = speed
    self.send_command(Command.SET_SPEED, [int(speed)])

  def set_effect(self, effect):
    print('in set_effect: ', effect)
    both = { **MONO_EFFECTS, **PRESET_EFFECTS }
    preset = clamp(both[effect])
    self._state.mode = preset
    self.send_command(Command.SET_PRESET, [int(preset)])

  def set_custom(self, custom):
    """
    Sets the light effect to the provided custom effect number

    :param custom: The custom effect to use. Valid values are 1 to 12. See the CustomEffect enum.
    """
    custom = clamp(custom, 1, 12)
    self._state.mode = custom
    self.send_command(Command.SET_CUSTOM, [int(custom)])

  def toggle(self):
    """
    Toggles the state of the light without checking the current state
    """
    self._state.is_on = not self._state.is_on
    self.send_command(Command.TOGGLE, [])

  def turn_on(self, **kwargs):
    print('turn on: ', kwargs)

    if ATTR_BRIGHTNESS in kwargs:
        self.set_brightness(kwargs[ATTR_BRIGHTNESS])

    if ATTR_WHITE_VALUE in kwargs:
        self.set_white(kwargs[ATTR_WHITE_VALUE])

    if ATTR_HS_COLOR in kwargs:
        r,g,b = color_util.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
        self.set_color(r, g, b)

    if ATTR_EFFECT in kwargs:
        self.set_effect(kwargs[ATTR_EFFECT])

    if self._state.is_on:
        print('already on')
    else:
        self.toggle()


  def turn_off(self):
    if self._state.is_on:
        self.toggle()
    else:
        print('already off')

  def set_segments(self, segments):
    """
    Sets the total number of segments. Total lights is segments * lights_per_segment.

    :param segments: The number of segments
    """
    self.send_command(Command.SET_SEGMENT_COUNT, [segments])

  def set_lights_per_segment(self, lights_per_segment):
    """
    Sets the number of lights per segment. Total lights is segments * lights_per_segment.

    :param lights_per_segment: The number of lights per segment
    """
    lights_per_segment_data = list(lights_per_segment.to_bytes(2, byteorder='little'))
    self.send_command(Command.SET_LIGHTS_PER_SEGMENT, lights_per_segment_data)

  def set_calculated_segments(self, total_lights, segments):
    """
    Helper function to automatically set the number of segments and lights per segment
    to reach the target total lights (rounded down to never exceed total_lights)

    Usually you know the total number of lights you have available on a light strip
    and want to split it into segments that take up the whole strip

    :param total_lights: The target total number of lights to use
    :param segments: The number of segments to split the total into
    """
    self.set_segments(segments)
    self.set_lights_per_segment(int(total_lights / segments))

  def send_command(self, command, data=[]):
    result = None
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._sock.settimeout(self._timeout)
    self._sock.connect((self._ip, self._port))

    min_data_len = 3
    padded_data = data + [0] * (min_data_len - len(data))
    raw_data = [CommandFlag.START, *padded_data, command, CommandFlag.END]
    self.send_bytes(raw_data)
    try:
        result = self._sock.recv(1024)
    except (socket.timeout, BrokenPipeError):
        pass

    self._sock.close()
    return result


  def send_bytes(self, data):
    """
    Helper method to send raw bytes directly to the controller

    Mostly for internal use, prefer the specific functions where possible
    """
    raw_data = bytes(data)

    attempts = 0
    while True:
      try:
        self._sock.sendall(raw_data)
        return
      except (socket.timeout, BrokenPipeError):
        print('in socket exeption....')
        if (attempts < self._retries):
          attempts += 1
          self._sock.close()
          self._sock.connect((self._ip, self._port))
        else:
          raise

  def update(self):
    attempts = 0
    while True:
      try:
        # Send the request for sync data
        response = self.send_command(Command.SYNC, [])

        # Extract the state data
        state = bytearray(response)
        self._state.update_from_sync(state)
        return
      except (socket.timeout, BrokenPipeError):
        # When there is an error with the socket, close the connection and connect again
        if attempts < self._retries:
          attempts += 1
        else:
          raise

  def __repr__(self):
    return f"""WikiLedShopLight @ {self._ip}:{self._port}
      state: {self._state}
      unique_id: {self._unique_id}
    """

  @property
  def unique_id(self):
      return self._unique_id

  @property
  def device_info(self):
    return {
      "identifiers": {('wifi-led-strip-controller', self._unique_id)},
      "manufacturer": "BTF-LIGHTING",
      "name": self._name,
      "model": 'sp108e',
    }

  @property
  def name(self):
      """Return the display name of this light."""
      return self._name

  @property
  def brightness(self):
    return self._state.brightness

  # @property
  # def white_value(self):
  #  return self._state.white

  @property
  def is_on(self):
    return self._state.is_on

  @property
  def hs_color(self):
    r,g,b = self._state.color
    h,s = color_util.color_RGB_to_hs(r, g, b)
    return (h, s)

  @property
  def effect_list(self):
    return list({ **MONO_EFFECTS, **PRESET_EFFECTS })

  @property
  def effect(self):
    both = { **MONO_EFFECTS, **PRESET_EFFECTS }
    current_effect = list(both.keys())[list(both.values()).index(self._state.mode)]
    return current_effect

  @property
  def supported_features(self):
    # return (SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_WHITE_VALUE | SUPPORT_EFFECT)
    return (SUPPORT_COLOR | SUPPORT_BRIGHTNESS | SUPPORT_EFFECT)
