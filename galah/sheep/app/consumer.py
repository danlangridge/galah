# Copyright 2012-2013 John Sullivan
# Copyright 2012-2013 Other contributers as noted in the CONTRIBUTERS file
#
# This file is part of Galah.
#
# Galah is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Galah is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Galah.  If not, see <http://www.gnu.org/licenses/>.

import zmq, logging, pyvz, universal, utility, universal, threading, tempfile, \
       subprocess, shutil, os.path, submit, json

# ZMQ constants for timeouts which are inexplicably missing from pyzmq
ZMQ_RCVTIMEO = 27
ZMQ_SNDTIMEO = 28

@universal.handleExiting
def run():
    log = logging.getLogger("galah.sheep.%s" % threading.currentThread().name)

    log.info("Consumer starting")
    
    # Set up the socket to recieve messages from the shepherd
    shepherd = universal.context.socket(zmq.DEALER)
    shepherd.linger = 0
    shepherd.setsockopt(ZMQ_RCVTIMEO, 5 * 1000)   
    shepherd.connect("tcp://%s:%d" % (universal.cmdOptions.shepherdAddress, 
                                      universal.cmdOptions.shepherdPort))
                                      
    # First tell the Shepherd what kind of system this consumer is running on
    # and what kind of tests it supports.
    shepherd.send_json(universal.environment)
   
    # Loop until the program is shutting down
    while not universal.exiting:
        # Get container id off of queue if there is one
        log.debug("Waiting for available VM")
        id = utility.dequeue(universal.containers)
        
        # Tell the shepherd we are ready for a test request
        shepherd.send_json("bleet")
        
        try: 
            # Recieve test request from the shepherd
            log.debug("Waiting for test request")
            addresses = utility.recv_json(shepherd)
            testRequest = addresses.pop()
    
            # Mark container as dirty before we do anything at all
            pyvz.setAttribute(id, "description", "galah-vm: dirty") 
        except universal.Exiting:
            # It's alright to just drop everything, the worst thing that could
            # happen is that some cleanup has to be done the next time the
            # program is run
            raise
        except:
            log.exception("Error occured during setup, destroying VM with "
                          "CTID %d" % id)
            
            pyvz.extirpateContainer(id)
            
            continue

        try:
            # Load the testables and test driver
            testableDirectory = submit.quickLoad(testRequest["testables"])
            driverDirectory = submit.quickLoad(testRequest["testDriver"])
                                
            # Inject file into VM from the testables location
            pyvz.injectFile(id, testableDirectory, "/home/tester/testables/",
                            zmove = False)
            
            # TODO: Permissions need to be set on the test driver so the
            # student's program can't access it.
            pyvz.injectFile(id, driverDirectory, "/home/tester/testDriver/",
                            zmove = False)
            
            # Inject Test Suite into VM
            pyvz.injectFile(id, "suite.py", "/home/tester/", zmove = False)
            
            # Execute suite.py
            log.debug("Running test suite")
            pyvz.runScript(id, "/home/tester/suite.py", "python")
            
            # Only certain fields get passed to the test suite, eliminate the
            # others
            testRequestClone = utility.filterDictionary(
                testRequest,
                ["actions", "config"]
            )
            
            # Socket to receive messages back from the VM
            vm = universal.context.socket(zmq.REQ)
            vm.setsockopt(ZMQ_RCVTIMEO, 5 * 1000)
            vm.connect("tcp://%s.%d:%d" % (universal.cmdOptions.vmSubnet, id,
                                           universal.cmdOptions.vmPort))
            
            # Send the test request to the VM. While we don't block here, even
            # if the VM doesn't accept the request immediately, ZMQ will ensure
            # that whenever the VM does start accepting requests it is sent.
            vm.send_json(testRequestClone, zmq.NOBLOCK)
            
            try:
                # Receive test results from the VM
                log.debug("Waiting for test results")
                testResult = utility.recv_json(vm, 60)
                
                log.debug("Test results recieved " + str(testResult))
            except zmq.ZMQError:
                log.info("Test Suite timed out")
                
                continue
            
            # Send the test result back to the shepherd
            shepherd.send_multipart(addresses + [json.dumps(testResult)])

            log.debug("Test results sent back to shepherd")

        except universal.Exiting:
            raise
        except:
            log.exception("Error in Consumer's Main Loop")
        finally:
            log.debug("Destroying VM with CTID %d" % id)
            
            pyvz.extirpateContainer(id)

    raise universal.Exiting()
