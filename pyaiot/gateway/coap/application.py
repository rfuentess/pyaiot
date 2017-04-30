# Copyright 2017 IoT-Lab Team
# Contributor(s) : see AUTHORS file
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Broker tornado application module."""

import json
import logging
from tornado.ioloop import PeriodicCallback
from tornado import web, gen
from tornado.websocket import websocket_connect

from .coap import CoapController

logger = logging.getLogger("pyaiot.gw.coap")


class CoapGatewayApplication(web.Application):
    """Tornado based web application providing live nodes on a network."""

    def __init__(self, options=None):
        assert options

        if options.debug:
            logger.setLevel(logging.DEBUG)

        handlers = []
        settings = {'debug': True}

        # Starts CoAP controller
        self._coap_controller = CoapController(
            on_message_cb=self.send_to_broker,
            max_time=options.max_time)
        PeriodicCallback(self._coap_controller.check_dead_nodes, 1000).start()

        # Create connection to broker
        self.create_broker_connection(
            "ws://{}:{}/broker".format(options.broker_host,
                                       options.broker_port))

        super().__init__(handlers, **settings)
        logger.info('CoAP gateway application started')

    @gen.coroutine
    def create_broker_connection(self, url):
        self.broker = yield websocket_connect(url)
        while True:
            message = yield self.broker.read_message()
            if message is None:
                logger.debug("Connection with broker lost.")
                break
            self.on_broker_message(message)

    def send_to_broker(self, message):
        """Send a message to the parent broker."""
        if self.broker is not None:
            logger.debug("Forwarding message '{}' to parent broker."
                         .format(message))
            self.broker.write_message(message)

    def on_broker_message(self, message, callback=None):
        """Handle a message received from the parent broker websocket."""
        logger.debug("Handling message '{}' received from broker."
                     .format(message))
        message = json.loads(message)

        if message['type'] == "new":
            # Received when a new client connects
            for node in self._coap_controller.nodes:
                self.broker.write_message(json.dumps({'command': 'new',
                                                      'node': node.address,
                                                      'origin': 'coap'}))
                self._coap_controller.discover_node(node)
        elif message['type'] == "update":
            # Received when a client update a node
            self._coap_controller.send_data_to_node(message['data'])
