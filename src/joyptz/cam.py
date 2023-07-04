"""
The code to control a camera from a joystick.
"""

import math
import logging

from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError

import zeep

LOG = logging.getLogger(__name__)


def zeep_pythonvalue(self, xmlvalue):
    return xmlvalue


class Camera:
    """The camera"""

    def __init__(self, config):
        self._request = None
        self._ptz = None
        self._token = None
        self._imaging = None
        self._imaging_token = None
        self._cam = None
        self.XMAX = 1
        self.XMIN = -1
        self.YMAX = 1
        self.YMIN = -1
        self._active_vector = [0.0, 0.0, 0.0]
        self._active_focus = 0.0
        self.init_camera(config)

    def init_camera(self, config):
        """Set up the camera."""


        mycam = ONVIFCamera(
            config["host"],
            config.get("port", 80),
            config.get("username"),
            config.get("password"),
        )
        self.cam = mycam
        media = mycam.create_media_service()
        ptz = mycam.create_ptz_service()
        self._ptz = ptz

        zeep.xsd.simple.AnySimpleType.pythonvalue = zeep_pythonvalue
        media_profile = media.GetProfiles()[0]

        # Get PTZ configuration options for getting continuous move range
        request = ptz.create_type("GetConfigurationOptions")
        request.ConfigurationToken = media_profile.PTZConfiguration.token
        ptz_configuration_options = ptz.GetConfigurationOptions(request)
        #print(ptz_configuration_options)

        image = mycam.create_imaging_service()
        request = image.create_type("GetImagingSettings")
        request.VideoSourceToken = media_profile.VideoSourceConfiguration.SourceToken
        self._imaging_token = media_profile.VideoSourceConfiguration.SourceToken
        # this info is kind of FYI during debugging/dev
        # current settings
        imaging_settings = image.GetImagingSettings(request)
        # valid options
        imaging_options = image.GetOptions(request)
        self._imaging = image

        # import ipdb
        # ipdb.set_trace()

        # load max ranges
        ranges = ptz_configuration_options.Spaces.ContinuousPanTiltVelocitySpace[0]
        self.XMAX = ranges.XRange.Max
        self.XMIN = ranges.XRange.Min
        self.YMAX = ranges.YRange.Max
        self.YMIN = ranges.YRange.Min

        request = ptz.create_type("ContinuousMove")
        request.ProfileToken = media_profile.token
        token = {"ProfileToken": media_profile.token}

        self._token = media_profile.token
        ptz.Stop(token)
        
        
        if request.Velocity is None:
            request.Velocity = ptz.GetStatus(token)


        self._request = request
        # import ipdb
        # ipdb.set_trace()

    def perform_move(self, vector):
        # if vector isn't that different from the last vector,
        # just leave the existing one to minimize jerkiness
        # of sending too many requests
        dist = math.sqrt(
            sum((x1 - x2) ** 2 for x1, x2 in zip(vector, self._active_vector))
        )
        # if dist < 0.05:
        #    # close enough. don't update anything
        #    return

        self._active_vector = vector
        x, y, zoom = vector  # assume unit vector
        print(x,y)
        s = {'list': {'KEY1': 'One'}}
        d = {'KEY2': 'Two'}
        s['list'].update(d)

      #  if(x!=0.0):
        self._request.Velocity = {'PanTilt': {'x': x * self.XMAX, 'y': y * self.YMAX}}
        #self._ptz.ContinuousMove(self._request)
       # else:
        if(zoom!=0.0):
            self._request.Velocity = {'Zoom':{'x':zoom}}
        self._ptz.ContinuousMove(self._request)


        # self._request.Velocity.PanTilt.x = x * self.XMAX
        # self._request.Velocity.PanTilt.y = y * self.YMAX
        #self._request.Velocity.Zoom.x = zoom
        self._ptz.ContinuousMove(self._request)

    def stop(self):

        # Check the vector before stopping to prevent sending stop command at each frame
        if any(self._active_vector):
            self._active_vector = [0.0, 0.0, 0.0]
            self._ptz.Stop({"ProfileToken": self._request.ProfileToken})

    def wiper_on(self):
        """Send an auxiliary command for tt:Wiper|On

        This command is shown in the GetNodes() results on ptz"""
        self._send_aux_cmd("tt:Wiper|On")

    def wiper_off(self):
        """Send an auxiliary command for tt:Wiper|Off"""
        self._send_aux_cmd("tt:Wiper|Off")

    def _send_aux_cmd(self, cmd):
        request = self._ptz.create_type("SendAuxiliaryCommand")
        request.ProfileToken = self._token
        request.AuxiliaryData = cmd
        resp = self._ptz.SendAuxiliaryCommand(request)

    def goto_preset(self, number):
        LOG.info("Going to preset %s", str(number))
        request = self._ptz.create_type("GotoPreset")
        request.ProfileToken = self._token
        request.PresetToken = str(number)
        try:
            resp = self._ptz.GotoPreset(request)
        except ONVIFError:
            print("Invalid preset {number}")

    def ir_on(self):
        LOG.info("IR ON")
        self.set_imaging_setting("IrCutFilter", "OFF")

    def ir_off(self):
        LOG.info("IR OFF")
        self.set_imaging_setting("IrCutFilter", "ON")

    def ir_auto(self):
        LOG.info("IR AUTO")
        self.set_imaging_setting("IrCutFilter", "AUTO")

    def set_imaging_setting(self, setting, val):
        request = self._imaging.create_type("SetImagingSettings")
        request.VideoSourceToken = self._imaging_token
        request.ImagingSettings = {setting: val}
        resp = self._imaging.SetImagingSettings(request)

    def set_focus_change(self, val):
        """skycam accepts speeds between -1 and 1."""
        dist = abs(val - self._active_focus)
        if dist < 0.05:
            return
        self._active_focus = val
        request = self._imaging.create_type("Move")
        request.VideoSourceToken = self._imaging_token
        request.Focus = {"Continuous": {"Speed": val}}
        resp = self._imaging.Move(request)
