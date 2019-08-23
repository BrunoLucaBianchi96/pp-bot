import os
import pingpongbot
from flask import Flask, request, make_response

app = Flask(__name__)
DEBUG = True
ppBot = pingpongbot.PingPongBot()


@app.route("/", methods=["GET", "POST"])
def home():
    """This route renders a hello world text."""
    # rendering text
    slack_event = request.get_json()

    print (str(slack_event))
    # ============= Slack URL Verification ============ #
    # In order to verify the url of our endpoint, Slack will send a challenge
    # token in a request and check for this token in the response our endpoint
    # sends back.
    #       For more info: https://api.slack.com/events/url_verification
    if "challenge" in slack_event:
        print("Received challenge")
        return make_response(slack_event["challenge"], 200, {"content_type":
                                                                 "application/json"
                                                             })
    if "event" in slack_event and slack_event["event"]["channel"] in ppBot.ALLOWED_CHANNELS:
        event_type = slack_event["event"]["type"]
        if event_type == 'message':
            # Then handle the event by event_type and have your bot respond
            return _event_handler(event_type, slack_event)

    return 'Hello World'


def _event_handler(event_type, slack_event):
    """
    A helper function that routes events from Slack to our Bot
    by event type and subtype.

    Parameters
    ----------
    event_type : str
        type of event received from Slack
    slack_event : dict
        JSON response from a Slack reaction event

    Returns
    ----------
    obj
        Response object with 200 - ok or 500 - No Event Handler error

    """
    team_id = slack_event["team_id"]

    # ============== Share Message Events ============= #
    # If the user has shared the onboarding message, the event type will be
    # message. We'll also need to check that this is a message that has been
    # shared by looking into the attachments for "is_shared".
    # if event_type == "message":
    #     user_id = slack_event["event"].get("user")
    #     return make_response("Welcome message updates with shared message", 200,)

    if not "subtype" in slack_event:
        user_id = slack_event["event"].get("user")
        event = slack_event["event"]
        message = ppBot.handle_command(event)
        if message:
            return make_response("Responded with: " + message, 200)
        else:
            return make_response("Event ignored", 200)

    # ============= Event Type Not Found! ============= #
    # If the event_type does not have a handler
    message = "You have not added an event handler for the %s" % event_type
    # Return a helpful error message
    return make_response(message, 200, {"X-Slack-No-Retry": 1})


@app.route("/bot", methods=["GET"])
def listening(**param):
    return str(param)


if __name__ == '__main__':
    app.run(debug=True, port=33507)
