#  This file is part of mylar.
#
#  mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with mylar.  If not, see <http://www.gnu.org/licenses/>.

from mylar import logger
import base64
import cherrypy
import urllib
import urllib2
import mylar
from httplib import HTTPSConnection
from urllib import urlencode
import os.path
import subprocess
import time
import lib.simplejson as simplejson
import json

# This was obviously all taken from headphones with great appreciation :)

class PROWL:

    keys = []
    priority = []

    def __init__(self):
        self.enabled = mylar.PROWL_ENABLED
        self.keys = mylar.PROWL_KEYS
        self.priority = mylar.PROWL_PRIORITY
        pass

    def conf(self, options):
        return cherrypy.config['config'].get('Prowl', options)

    def notify(self, message, event, module=None):
        if not mylar.PROWL_ENABLED:
            return

        if module is None:
            module = ''
        module += '[NOTIFIER]'

        http_handler = HTTPSConnection("api.prowlapp.com")

        data = {'apikey': mylar.PROWL_KEYS,
                'application': 'Mylar',
                'event': event,
                'description': message.encode("utf-8"),
                'priority': mylar.PROWL_PRIORITY}

        http_handler.request("POST",
                                "/publicapi/add",
                                headers = {'Content-type': "application/x-www-form-urlencoded"},
                                body = urlencode(data))
        response = http_handler.getresponse()
        request_status = response.status

        if request_status == 200:
                logger.info(module + ' Prowl notifications sent.')
                return True
        elif request_status == 401:
                logger.info(module + ' Prowl auth failed: %s' % response.reason)
                return False
        else:
                logger.info(module + ' Prowl notification failed.')
                return False

    def updateLibrary(self):
        #For uniformity reasons not removed
        return

    def test(self, keys, priority):

        self.enabled = True
        self.keys = keys
        self.priority = priority

        self.notify('ZOMG Lazors Pewpewpew!', 'Test Message')

class NMA:

    def __init__(self):

        self.apikey = mylar.NMA_APIKEY
        self.priority = mylar.NMA_PRIORITY

    def _send(self, data, module):

        url_data = urllib.urlencode(data)
        url = 'https://www.notifymyandroid.com/publicapi/notify'

        req = urllib2.Request(url, url_data)

        try:
            handle = urllib2.urlopen(req)
        except Exception, e:
            logger.warn(module + ' Error opening NotifyMyAndroid url: ' % e)
            return

        response = handle.read().decode(mylar.SYS_ENCODING)

        return response

    def notify(self, snline=None, prline=None, prline2=None, snatched_nzb=None, sent_to=None, prov=None, module=None):

        if module is None:
            module = ''
        module += '[NOTIFIER]'

        apikey = self.apikey
        priority = self.priority

        if snatched_nzb:
            if snatched_nzb[-1] == '\.': snatched_nzb = snatched_nzb[:-1]
            event = snline
            description = "Mylar has snatched: " + snatched_nzb + " from " + prov + " and has sent it to " + sent_to
        else:
            event = prline
            description = prline2

        data = {'apikey': apikey, 'application': 'Mylar', 'event': event, 'description': description, 'priority': priority}

        logger.info(module + ' Sending notification request to NotifyMyAndroid')
        request = self._send(data, module)

        if not request:
            logger.warn(module + ' Error sending notification request to NotifyMyAndroid')

# 2013-04-01 Added Pushover.net notifications, based on copy of Prowl class above.
# No extra care has been put into API friendliness at the moment (read: https://pushover.net/api#friendly)
class PUSHOVER:

    def __init__(self):
        self.enabled = mylar.PUSHOVER_ENABLED
        if mylar.PUSHOVER_APIKEY is None or mylar.PUSHOVER_APIKEY == 'None':
            self.apikey = 'a1KZ1L7d8JKdrtHcUR6eFoW2XGBmwG'
        else:
            self.apikey = mylar.PUSHOVER_APIKEY
        self.userkey = mylar.PUSHOVER_USERKEY
        self.priority = mylar.PUSHOVER_PRIORITY
        # other API options:
        # self.device_id = mylar.PUSHOVER_DEVICE_ID
        # device - option for specifying which of your registered devices Mylar should send to. No option given, it sends to all devices on Pushover (default)
        # URL / URL_TITLE (both for use with the COPS/OPDS server I'm building maybe?)
        # Sound - name of soundfile to override default sound choice

    # not sure if this is needed for Pushover

    #def conf(self, options):
    # return cherrypy.config['config'].get('Pushover', options)

    def notify(self, message, event, module=None):
        if not mylar.PUSHOVER_ENABLED:
            return
        if module is None:
            module = ''
        module += '[NOTIFIER]'

        http_handler = HTTPSConnection("api.pushover.net:443")

        data = {'token': mylar.PUSHOVER_APIKEY,
                'user': mylar.PUSHOVER_USERKEY,
                'message': message.encode("utf-8"),
                'title': event,
                'priority': mylar.PUSHOVER_PRIORITY}

        http_handler.request("POST",
                                "/1/messages.json",
                                body = urlencode(data),
                                headers = {'Content-type': "application/x-www-form-urlencoded"}
                                )
        response = http_handler.getresponse()
        request_status = response.status

        logger.fdebug(u"PushOver response status: %r" % request_status)
        logger.fdebug(u"PushOver response headers: %r" % response.getheaders())
        logger.fdebug(u"PushOver response body: %r" % response.read())


        if request_status == 200:
                logger.info(module + ' Pushover notifications sent.')
                return True
        elif request_status == 401:
                logger.info(module + 'Pushover auth failed: %s' % response.reason)
                return False
        else:
                logger.info(module + ' Pushover notification failed.')
                return False

    def test(self, apikey, userkey, priority):

        self.enabled = True
        self.apikey = apikey
        self.userkey = userkey
        self.priority = priority

        self.notify('ZOMG Lazors Pewpewpew!', 'Test Message')


class BOXCAR:

    #new BoxCar2 API
    def __init__(self):

        self.url = 'https://new.boxcar.io/api/notifications'

    def _sendBoxcar(self, msg, title, module):

        """
        Sends a boxcar notification to the address provided

        msg: The message to send (unicode)
        title: The title of the message

        returns: True if the message succeeded, False otherwise
        """

        try:

            data = urllib.urlencode({
                'user_credentials': mylar.BOXCAR_TOKEN,
                'notification[title]': title.encode('utf-8').strip(),
                'notification[long_message]': msg.encode('utf-8'),
                'notification[sound]': "done"
                })

            req = urllib2.Request(self.url)
            handle = urllib2.urlopen(req, data)
            handle.close()
            return True

        except urllib2.URLError, e:
            # if we get an error back that doesn't have an error code then who knows what's really happening
            if not hasattr(e, 'code'):
                logger.error(module + 'Boxcar2 notification failed. %s' % e)
            # If you receive an HTTP status code of 400, it is because you failed to send the proper parameters
            elif e.code == 400:
                logger.info(module + ' Wrong data sent to boxcar')
                logger.info(module + ' data:' + data)
            else:
                logger.error(module + ' Boxcar2 notification failed. Error code: ' + str(e.code))
            return False

        logger.fdebug(module + ' Boxcar2 notification successful.')
        return True

    def notify(self, prline=None, prline2=None, sent_to=None, snatched_nzb=None, force=False, module=None, snline=None):
        """
        Sends a boxcar notification based on the provided info or SB config

        title: The title of the notification to send
        message: The message string to send
        force: If True then the notification will be sent even if Boxcar is disabled in the config
        """
        if module is None:
            module = ''
        module += '[NOTIFIER]'

        if not mylar.BOXCAR_ENABLED and not force:
            logger.fdebug(module + ' Notification for Boxcar not enabled, skipping this notification.')
            return False

        # if no username was given then use the one from the config
        if snatched_nzb:
            title = snline
            message = "Mylar has snatched: " + snatched_nzb + " and has sent it to " + sent_to
        else:
            title = prline
            message = prline2

        logger.info(module + ' Sending notification to Boxcar2')

        self._sendBoxcar(message, title, module)
        return True

class PUSHBULLET:

    def __init__(self):
        self.apikey = mylar.PUSHBULLET_APIKEY
        self.deviceid = mylar.PUSHBULLET_DEVICEID

    def get_devices(self, api):
        return self.notify(method="GET")

    def notify(self, snline=None, prline=None, prline2=None, snatched=None, sent_to=None, prov=None, module=None, method=None):
        if not mylar.PUSHBULLET_ENABLED:
            return
        if module is None:
            module = ''
        module += '[NOTIFIER]'

        http_handler = HTTPSConnection("api.pushbullet.com")

        if method == 'GET':
            uri = '/v2/devices'
        else:
            method = 'POST'
            uri = '/v2/pushes'

        authString = base64.b64encode(self.apikey + ":")

        if method == 'GET':
            http_handler.request(method, uri, None, headers={'Authorization': 'Basic %s:' % authString})
        else:
            if snatched:
                if snatched[-1] == '.': snatched = snatched[:-1]
                event = snline
                message = "Mylar has snatched: " + snatched + " from " + prov + " and has sent it to " + sent_to
            else:
                event = prline + ' complete!'
                message = prline2

            data = {'type': "note", #'device_iden': self.deviceid,
                    'title': event.encode('utf-8'), #"mylar",
                    'body': message.encode('utf-8')}

        http_handler.request("POST",
                                "/v2/pushes",
                                headers = {'Content-type': "application/json",
                                           'Authorization': 'Basic %s' % base64.b64encode(mylar.PUSHBULLET_APIKEY + ":")},
                                body = json.dumps(data))

        response = http_handler.getresponse()
        request_body = response.read()
        request_status = response.status
        #logger.fdebug(u"PushBullet response status: %r" % request_status)
        #logger.fdebug(u"PushBullet response headers: %r" % response.getheaders())
        #logger.fdebug(u"PushBullet response body: %r" % response.read())

        if request_status == 200:
            if method == 'GET':
                return request_body
            else:
                logger.info(module + ' PushBullet notifications sent.')
                return True
        elif request_status >= 400 and request_status < 500:
            logger.error(module + ' PushBullet request failed: %s' % response.reason)
            return False
        else:
            logger.error(module + ' PushBullet notification failed serverside.')
            return False

    def test(self, apikey, deviceid):

        self.enabled = True
        self.apikey = apikey
        self.deviceid = deviceid

        self.notify('Main Screen Activate', 'Test Message')

