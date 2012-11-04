## The Actual View ##
from galah.web.galahweb import app
from flask.ext.login import current_user
from galah.web.galahweb.auth import account_type_required
from bson.objectid import ObjectId
from bson.errors import InvalidId
from flask import abort, render_template, request, flash, redirect, jsonify, \
                  url_for
from galah.db.models import Submission, Assignment
from galah.web.galahweb.util import is_url_on_site
from werkzeug import secure_filename
import os.path
import subprocess
import datetime
import shutil
import tempfile
import datetime

from _view_assignment import SimpleArchiveForm

SUBMISSION_DIRECTORY = "/var/local/galah.web/submissions/"
assert SUBMISSION_DIRECTORY[0] == "/" # Directory must be given as absolute path
    
def abort_new_submission(submission):
    """
    Deletes and cleans up a submission THAT HAS NOT YET BEEN SAVED to Mongo by
    deleting the testables directory, etc.
    
    Call this if a created submission is found to be invalid during processing.
    
    """
    
    if submission.testables:
        # Delete the directory
        shutil.rmtree(submission.testables)

@app.route("/assignments/<assignment_id>/upload", methods = ["POST"])
@account_type_required(("student", "teacher"))
def upload_submission(assignment_id):
    # Convert the assignment in the URL into an ObjectId
    try:
        id = ObjectId(assignment_id)
    except InvalidId:
        app.logger.debug("Invalid ID: Malformed.")
        
        abort(404)
    
    # Ensure that an assignment with the provided id actually exists
    try:
        assignment = Assignment.objects.get(id = id)
    except Assignment.DoesNotExist:
        app.logger.debug("Invalid ID: Assignment does not exist.")
        
        abort(404)
    
    # Figure out where we should redirect the user to once we're done.
    redirect_to = request.args.get("next") or request.referrer

    if not is_url_on_site(app, redirect_to):
        # Default going back to the assignment screen
        redirect_to = url_for(
            "view_assignment",
            assignment_id = assignment_id
        )
    
    # Check if the assignment's cutoff date has passed
    if assignment.due_cutoff and \
            assignment.due_cutoff < datetime.datetime.today():
        return craft_response(
            error = "The cutoff date has already passed, your submission was "
                    "not accepted."
        )

    new_submission = Submission(
        assignment = id,
        user = current_user.id,
        timestamp = datetime.datetime.now(),
        marked_for_grading = True
    )
    new_submission.id = ObjectId()

    # Craft a unique directory path where we will store the new submission. We
    # are guarenteed an ObjectId is unique. However we are not guarenteed that
    # we will have the proper permissions and that we will be able to make the
    # directory thus this could error because of that.
    new_submission.testables = os.path.join(
        SUBMISSION_DIRECTORY, str(new_submission.id)
    )
    os.makedirs(new_submission.testables)

    form = SimpleArchiveForm()
    if not form.validate_on_submit():
        flash("The files you passed in were invalid.", category = "error")
        return redirect(redirect_to)


    # Save each file the user uploaded into the submissions directory
    for i in form.archive.entries:
        if not i.data.filename:
            continue

        # Figure out where we want to save the user's file
        file_path = os.path.join(
            new_submission.testables, secure_filename(i.data.filename)
        )

        app.logger.debug("Saving user's file to %s." % file_path)

        # Do the actual saving
        i.data.save(file_path)
    
    new_submission.uploaded_filenames.extend(
        i.data.filename for i in form.archive.entries if i.data.filename
    )

    # Persist! Otherwise nobody will know what happened this day.
    new_submission.save()
    
    # Communicate to the next page what submission was just added.
    flash(new_submission.id, category = "new_submission")
    
    # Everything seems to have gone well
    return redirect(redirect_to)
