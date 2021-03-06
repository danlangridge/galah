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

import zmq, json, subprocess, logging, os.path, sys

# Port that this VM uses to listen for the test server.
testServerPort = 6668

def main():
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s.%(levelname)s: %(message)s"))
    topLog = logging.getLogger("galah")
    topLog.setLevel(logging.DEBUG)
    topLog.addHandler(sh)
    
    log = logging.getLogger("galah.vm-suite")
    log.debug("Test suite starting.")
    
    # Socket connection to the test server and VM
    context = zmq.Context()
    
    # Socket to talk to test server and VM
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:%d" % (testServerPort))
    
    log.debug("Connected (?) to testServer")
    
    # Recieve test request from the test server
    log.debug("Waiting for test request")
    testRequest = socket.recv()
    
    log.debug("Running test driver")
    
    os.chdir("/home/tester/")
    
    driverPath = "testDriver/main"
    if not os.path.exists(driverPath):
        log.error("Test driver does not exist.")
        
        socket.send_json({"error": "Test driver does not exist."})
        
        sys.exit(1)
    
    # Run testdriver on student script
    testDriverProc = subprocess.Popen([driverPath],
                                      stdout = subprocess.PIPE,
                                      stdin = subprocess.PIPE,
                                      cwd = "/home/tester/")
    
    # Test result, JSON object encoded as string
    result = testDriverProc.communicate(testRequest)[0]
    
    # Send test results to test server
    log.debug("Sending test result")
    socket.send(result)

if __name__ == "__main__":
    main()
