#!/usr/bin/env python

import requests

# We'll need to store any cookies the server gives us (mainly the auth cookie)
# and requests' sessions give us a nice way to do that.
session = requests.session()

# The default configuration settings
config = {
    "galah_host": "http://localhost:5000",
    "galah_home": "~/.galah"
}

def to_json(obj):
    """
    Serializes an object into a JSON representation. The returned string will be
    compressed appropriately for network transfer.
    
    """

    import json
    
    return json.dumps(obj, separators = (",", ":"))

def form_call(api_name, *args, **kwargs):
    """
    Creates a tuple or dict (depending on the existence of keyword arguments)
    that can be serialized to JSON and sent to galah.api.
    
    """
    
    if not kwargs:
        return (api_name, ) + args
    else:
        # kwargs is basically already what we want, we just need to add the
        # positional arguments and name of the API call.
        kwargs.update({"api_name": api_name, "args": args})
        
        return kwargs

def save_cookiejar(jar, user):
    """
    Save the cookies in the current session to the galah temp directory.

    """

    import pickle

    jar_path = os.path.join(config["galah_home"], "tmp", "cookiejar")

    with open(jar_path, "w") as f:
        pickle.dump((session.cookies, user), f)

def load_cookiejar():
    """
    Load the cookies from an old session from the galah temp directory.

    """

    import pickle

    jar_path = os.path.join(config["galah_home"], "tmp", "cookiejar")

    try:
        with open(jar_path, "r") as f:
            return pickle.load(f)
    except IOError:
        pass

    return (session.cookies, None)

def login(email, password):
    """
    Attempts to authenticate with Galah using the given credentials.

    """

    request = session.post(
        config["galah_host"] + "/api/login",
        data = {"email": email, "password": password}
    )
    
    request.raise_for_status()
    
    # Check if we successfully logged in.
    if request.headers["X-CallSuccess"] != "True":
        raise RuntimeError(request.text)
    
    # Nothing bad happened, go ahead and return what the server sent back
    return request.text

def oauth2login(oauth):
    """
    Attempts to authenticate user for Galah using Google OAuth2.

    """

    # Google OAuth2
    from oauth2client.tools import run
    from oauth2client.file import Storage
    from oauth2client.client import OAuth2WebServerFlow
    import httplib2, json

    # Get client_id and client_secret from server
    try:
        google_api_keys = json.loads(call_backend("get_oauth2_keys"))
    except requests.exceptions.ConnectionError as e:
        print >> sys.stderr, "Could not connect with the given url '%s':" \
                % config["galah_host"]
        print >> sys.stderr, "\t" + str(e)

        exit(1)

    # Google OAuth2 flow object to get user's email.
    flow = OAuth2WebServerFlow(
        client_id=google_api_keys["CLIENT_ID"],
        client_secret=google_api_keys["CLIENT_SECRET"],
        scope='https://www.googleapis.com/auth/userinfo.email',
        user_agent='Galah')

    storage = Storage(".credentials")

    # Get new credentials from user
    credentials = run(flow, storage)

    # If the credentials are authorized, they've given permission.
    http = httplib2.Http()
    http = credentials.authorize(http)

    # Extract email and email verification
    id_token = credentials.id_token
    email = id_token["email"]
    verified_email = id_token["verified_email"]
    access_token = credentials.access_token

    if verified_email != "true":
        raise RuntimeError("Could not verify email")

    request = session.post(
        config["galah_host"] + "/api/login",
        data = {"email":email, "access_token":access_token}
    )

    request.raise_for_status()
    
    # Check if we successfully logged in.
    if request.headers["X-CallSuccess"] != "True":
        raise RuntimeError(request.text)

    # User logged in successfully so return email they authenticated as.
    return email

def call_backend(api_name, *args, **kwargs):
    return _call(False, api_name, *args, **kwargs)

def call(api_name, *args, **kwargs):
    return _call(True, api_name, *args, **kwargs)

def _call(interactive, api_name, *args, **kwargs):
    """
    Makes an API call to the server with the given arguments. This function will
    block until the server sends its response.

    Iff interactive is True then call will take care of printing to the console
    itself, and will prompt the user if the server wants to push any downloads
    down, None is returned. Otherwise, pushes will be ignored and the text sent
    from the server will be returned, nothing will be printed to the console.
    
    """
    
    # May throw a requests.ConnectionError here if galah.api is unavailable.
    request = session.post(
        config["galah_host"] + "/api/call",
        data = to_json(form_call(api_name, *args, **kwargs)),
        headers = {"Content-Type": "application/json"}
    )
    
    # Will throw a requests.URLError or requests.HTTPError here if either
    # occurred.
    request.raise_for_status()
    
    # Currently only textual data is ever returned but other types of data may
    # be returned in the future. If this warning goes off that means that this
    # script needs to be updated to a new version.
    if not request.headers["Content-Type"].startswith("text/plain"):
        from warnings import warn

        warn(
            "Expecting text/plain content, got %s. You may need to update this "
            "program." % request.headers["Content-Type"].split(";")[0]
        )
    
    # Check if the server encountered an error processing the request.
    # Unfortunately the status code can't be set to 500 on the server side
    # because of some issues with Flask, so we have this custom header.
    if request.headers["X-CallSuccess"] != "True":
        raise RuntimeError(request.text)

    # If we're not in interactive mode, our job is done already.
    if not interactive:
        return request.text

    print request.text

    # Check if the server wants us to download a file
    if "X-Download" in request.headers:
        default_name = request.headers.get(
            "X-Download-DefaultName", "downloaded_file"
        )

        print "The server is requesting that you download a file..."

        save_to = raw_input(
            "Where would you like to save it (default: ./%s)?: " % default_name
        )

        # If they don't type anything in, go with the default.
        if not save_to:
            save_to = "./" + default_name

        if os.path.isfile(save_to):
            confirmation = raw_input(
                "File %s already exists, would you like to overwrite it "
                "(y, n)? " % save_to
            )

            if not confirmation.startswith("y"):
                exit("Aborting.")

        # Actually grab the file from the server
        while True:
            file_request = session.get(
                config["galah_host"] + "/" + request.headers["X-Download"]
            )
            
            if file_request.status_code == requests.codes.ok:
                break

            print "Download not ready yet, waiting for server... Retrying " \
                  "in 2 seconds..."

            import time
            time.sleep(2)

        with open(save_to, "wb") as download_file:
            download_file.write(file_request.content)

        print "File saved to %s." % save_to

import sys
def parse_arguments(args = sys.argv[1:]):
    from optparse import OptionParser, make_option

    option_list = [
        make_option(
            "--user", "-u", metavar = "USERNAME",
            help = "The username to authenticate with. The password should be "
                   "available in the evironmental variable GALAH_PASSWORD "
                   "if this option is used."
        ),
        make_option(
            "--config", "-c", metavar = "FILE",
            help = "The configuration file to use. To show the default "
                   "locations this script searches for, use --config-path."
        ),
        make_option(
            "--shell", "-s", action = "store_true",
            help = "If specified, you will be placed in an interactive "
                   "bash shell that will allow you to execute api commands as "
                   "if they were regular system commands."
        ),
        make_option(
            "--oauth", "-o", action = "store_true",
            help = "If specified, you will be able to login using your google "
                   "account as long as the email matches one stored in the db."
        ),
        make_option(
            "--config-path", action = "store_true", dest = "show_config_path",
            help = "If sepcified, all the locations this script would check "
                   "for the config file at will be displayed, then the script "
                   "will exit."
        )
    ]

    parser = OptionParser(
        description = "Command line interface to Galah for use by instructors "
                      "and administrators.",
        option_list = option_list,
        epilog = "Example usage in bash: GALAH_PASSWORD=test python "
                 "api_client.py -u john@doe.com get_submissions "
                 "SOME0ASSIGNMENT0ID"
    )

    options, args = parser.parse_args(args)

    if not options.shell and not options.show_config_path and len(args) == 0:
        parser.error("At least one argument must be supplied.")

    return (options, args)

def parse_configuration(config_file):
    import json

    config = json.load(config_file)

    return config

def exec_to_shell():
    # The name of the currently executing script (ex: api_client.py)
    script_location, script_name = os.path.split(__file__)
    script_location = os.path.abspath(script_location)

    import json

    # Retrieve all of the available commands from the server
    try:
        api_info = json.loads(call_backend("get_api_info"))
    except requests.exceptions.ConnectionError as e:
        print >> sys.stderr, "Could not connect with the given url '%s':" \
                % config["galah_host"]
        print >> sys.stderr, "\t" + str(e)

        exit(1)

    commands = [i["name"] for i in api_info]

    import tempfile
    rcfile, rcfile_path = tempfile.mkstemp("rc")

    # Wrap the file descripter we get back with a nice python file object
    rcfile = os.fdopen(rcfile, "w")

    # Add the location of the api client to the PATH
    print >> rcfile, 'PATH="%s:$PATH"' % script_location

    # Add the location of the man files to the MANPATH
    print >> rcfile, "export MANPATH=./man/:`manpath`"

    # Add aliases for each command that just wrap the api client
    for i in commands:
        print >> rcfile, 'alias %s="%s %s"' % (i, script_name, i)

    # Change the prompt a little bit so users know their in a modified shell
    print >> rcfile, 'PS1="\\[\033[1;34m\\](Galah API) $PS1\\[\033[0m\\]"'

    # Manually ensure that there's nothing buffered as no cleanup will occur
    # when we exec below.
    rcfile.flush()
    rcfile.close()

    os.execlp("bash", "bash", "--rcfile", rcfile_path)

import os
def main():
    # Parse any and all command line arguments
    options, args = parse_arguments()

    # Construct the ordered list of places to look for the galah config file.
    possible_config_paths = [
        "~/.galah/config/api_client.config",
        "/etc/galah/api_client.config",
        "./api_client.config"
    ]

    if "GALAH_CONFIG_PATH" in os.environ:
        possible_config_paths = os.environ["GALAH_CONFIG_PATH"].split(":") + \
                possible_config_paths

    if options.show_config_path:
        print "Places to search for configuration (top first):"
        for i in possible_config_paths:
            print "\t%s" % i

        exit(0)

    if options.config:
        config_file_path = options.config
    else:
        for i in possible_config_paths:
            resolved_path = os.path.abspath(os.path.expanduser(i))

            if os.path.isfile(resolved_path):
                config_file_path = resolved_path

    if config_file_path:
        try:
            with open(config_file_path) as config_file: 
                config.update(parse_configuration(config_file))
        except (IOError, KeyError):
            exit("File '%s' could not be opened for reading." % config_file)

    # If the user used ~ in the galah_home path in the config, expand it.
    config["galah_home"] = os.path.expanduser(config["galah_home"])

    if options.shell:
        exec_to_shell()

    # Figure out what credentials we want to use.
    user = options.user or config.get("user") or "Anonymous"
    print "--Acting as user %s--" % user

    # Before we do any network calls, load up any cookies left over from the
    # last time we ran the API client.
    old_jar = load_cookiejar()

    if old_jar[1] == user:
        session.cookies = old_jar[0]

    # I'm going to try and extract all the of the named arguments the user
    # passed in.
    named_args = {}

    # Go through each argument and detect if it's a key value pair
    import re
    to_delete = []
    for i in range(len(args)):
        match = re.match(r"(?P<name>[a-z_]+)(?!\\)=(?P<value>.*)", args[i])

        if match:
            named_args[match.group("name")] = match.group("value")
            to_delete.append(i)

        args[i] = args[i].replace("\\=", "=")

    # Delete all of the key value paris.
    for i in to_delete:
        del args[i]

    def do_api_call():
        try:
            # This function actually outputs the result of the call to the
            # console.
            call(*args, **named_args)
        except requests.exceptions.ConnectionError as e:
            print >> sys.stderr, "Could not connect with the given url '%s':" \
                    % config["galah_host"]
            print >> sys.stderr, "\t" + str(e)

            exit(1)

    try:
        # Try to execute the API call. We can fail here for two reasons: the API
        # command throws some error, or we aren't logged in.
        do_api_call()

        # If the above call didn't error, we're all set.
        exit(0)
    except RuntimeError as e:
        # Check to see if we failed because we're not logged in.
        import re
        logged_in = not bool(re.match( 
            "An error occurred processing your request: Only [A-Za-z ]+ users "
            "are allowed to call [A-Za-z_]+",
            str(e)
        ))

        # If we were already logged in or the user didn't give us any
        # credentials, just print out the error message.
        if logged_in or not user:
            exit(str(e))

    # If we got this far, we failed the above command because we're not logged
    # in, so now we will try to login, and then we'll try the command again.

    if "GALAH_PASSWORD" in os.environ and "password" in config:
        print >> sys.stderr, (
            "Warning: Password specified in both the GALAH_PASSWORD "
            "environmental variable and the configuration file. Using "
            "GALAH_PASSWORD."
        )

    password = os.environ.get("GALAH_PASSWORD") or config.get("password")
    oauth = options.oauth

    # If they specify to login via a Google Account, log them in by OAuth2
    if bool(oauth):
        try:
            user = oauth2login(oauth)

            save_cookiejar(session.cookies, user)
        except RuntimeError:
            print >> sys.stderr, "Could not authenticate user with provided " \
                  "email."

            exit(1)

    else:
        # If they didn't specify a password anywhere, go ahead and prompt
        # them for one.
        if not password:
            import getpass
            password = getpass.getpass("Please enter password for user %s: " 
                                       % user)

        if not password:
            exit("Could not log in as %s. No password given." % user)

        try:
            login(user, password)

            # We logged in successfully, save whatever cookies the user gave us
            # to the disk.
            save_cookiejar(session.cookies, user)
        except requests.exceptions.ConnectionError as e:
            print >> sys.stderr, "Could not connect with the given url '%s':" \
                % config["galah_host"]
            print >> sys.stderr, "\t" + str(e)

            exit(1)
        except RuntimeError:
            print >> sys.stderr, "Could not log in with provided user name " \
                "and password."

            exit(1)

    try:
        # Do the API command again.
        do_api_call()
    except RuntimeError as e2:
        # If we fail again, just print out the message, it's not a login
        # issue.
        print >> sys.stderr, str(e2)

if __name__ == "__main__":
    main()
