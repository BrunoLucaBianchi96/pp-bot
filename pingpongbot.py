import time
from random import randrange
import json
import os
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient('xoxb-23700961808-734416636567-zbV8fobU92xCK0VXzmAIJ2oF')
# bot's user ID in Slack: value is assigned after the bot starts up
pingpongbot_id = None

# constants
RTM_READ_DELAY = 0.5  # 0.5 second delay between reading from RTM
TEST_CHANNEL = "CMM7PDSUX"
USERS_LIST = []
USER_DATA = {}
ACTIVE_CHALLENGES = []
ACTIVE_MATCHES = []
PLAYERS_IN_A_MATCH = []
FILE_CACHE = {}
BASE_ELO = 0
ELO_VARIANCE = 32
TEST_USER = 'U8C1J0VFA'
LEADERBOARD_FILE_NAME = 'leaderboard.json'
AUTO_SHOW_SCOREBOARD_ON_LOSS = True
MINIMUM_ELO_GAIN = 10
DEBUG_MODE = True
TAUNTS_LIST = ["No sabes lo que {0} dijo de tu vieja, {1}!",
               "Lo que te dijo {0}! En mi barrio matan por menos, {1}",
               "{0} dijo que sos re mediocre en el ping pong, {1}",
               "{0} dijo que te apesta el aliento, {1}",
               "{0} dijo que si le pasaras una cartita que dice 'Queres ser mi amigo?' marcaría la casilla de 'No'! Hacete respetar, {1}",
               "{0} dijo que {1} va al baño y no tira la cadena",
               "{0} dijo que te gusta PHP, {1}"]


def parse_bot_commands(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and channel.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        if event["type"] == "message" and not "subtype" in event:
            message = parse_direct_mention(event["text"])
            # print(event)
            return message, event["channel"], event["user"]

    return None, None, None


def parse_direct_mention(message_text):
    """
        Finds a message stating with pp
    """
    matches = None, None
    if str(message_text).startswith("pp "):
        matches = message_text.split()

    return (matches[1], matches[2:]) if matches else (None, None)


def cancel_match_for(user_to_remove):
    """
    Cancels the match that user_to_remove is a part of, and returns the other player
    :param user_to_remove:  -- The userId to remove from the pool of matches
    :return: -- The userId of the other player involved
    """
    global PLAYERS_IN_A_MATCH
    global ACTIVE_MATCHES
    print("Removing player " + user_to_remove + "from " + str(PLAYERS_IN_A_MATCH))
    PLAYERS_IN_A_MATCH.remove(user_to_remove)
    other_player = None
    print("ACTIVE MATCHES " + str(ACTIVE_MATCHES))
    for match in ACTIVE_MATCHES:
        for each_user in match:
            if each_user == user_to_remove:
                other_player = get_other_user(user_to_remove, match)
                print("Removing player " + other_player + " from " + str(PLAYERS_IN_A_MATCH))
                PLAYERS_IN_A_MATCH.remove(other_player)
                print("PLAYERS IN A MATCH NOW " + str(PLAYERS_IN_A_MATCH))
                ACTIVE_MATCHES.remove(match)
                print("ACTIVE MATCHES NOW " + str(ACTIVE_MATCHES))

    return other_player


def cancel_challenge_for(cancelling_user):
    """
    Cancels any present challenges for this user

    :param cancelling_user:
    :return:
    """
    global ACTIVE_CHALLENGES
    for challenge in ACTIVE_CHALLENGES:
        if challenge["challenged"] == cancelling_user or challenge["challenger"] == cancelling_user:
            print("Found a challenge to cancel: " + str(challenge))
            ACTIVE_CHALLENGES.remove(challenge)
            return



def cancel_challenge_or_match(cancelling_user):
    if is_in_a_match(cancelling_user):
        cancel_match_for(cancelling_user)
        return "Match cancelled"

    if has_active_challenge(cancelling_user):
        cancel_challenge_for(cancelling_user)
        return "Challenge cancelled"

    return 'Nothing to cancel'


def random_taunt(taunting_user, mentioned_user):
    taunt_id = randrange(len(TAUNTS_LIST))
    print("Taunt id " + str(taunt_id) + " Taunt list length " + str(len(TAUNTS_LIST)))
    return TAUNTS_LIST[taunt_id].format(taunting_user, mentioned_user)


def handle_command(command, channel, user):
    """
        Executes bot command if the command is known
    """
    default_response = ':why-not: DONT UNDERTIENDO COMANDO!! :why-not:'
    response = None
    action = command[0]

    params = command[1]

    if action == 'test':
        response = "ITS ALIVE!"
    if action == 'challenge':
        response = handle_challenge(user, params)
    if action == 'lost':
        response = handle_loss(user)
    if action == 'accept':
        response = accept_challenge(user)
    if action == 'leaderboard':
        response = print_leaderboard()
    if action == 'cancel':
        response = cancel_challenge_or_match(user)
    if action == 'acceptAs' and DEBUG_MODE:
        response = accept_challenge(strip_mention(params[0]))
    if action == 'taunt':
        response = random_taunt(mention(user), params[0])

    # Sends the response back to the channel
    slack_client.api_call(
        "chat.postMessage",
        channel=channel,
        text=response or default_response
    )

    return response or default_response


def is_in_a_match(enemy_user):
    return enemy_user in PLAYERS_IN_A_MATCH


def handle_challenge(user, params):
    enemy_user = params[0]
    if has_active_challenge(user):
        return 'You have a pending challenge!'

    if has_active_challenge(enemy_user):
        return str(USER_DATA[enemy_user] + ' has an active challenge ')

    if is_in_a_match(user):
        return USER_DATA[user] + " is in a match"

    if is_in_a_match(enemy_user):
        return USER_DATA[enemy_user] + " is in a match"

    create_challenge(user, enemy_user)

    return 'Te desafiaron a un duelo a muerte con cuchillos, ' + enemy_user + '!'


def get_other_user(user_to_remove, match):
    return match[1] if match[0] == user_to_remove else match[0]


def calculate_expected_scores(loser, winner):
    print("Loser: " + str(loser))
    print("Winner: " + str(loser))
    loser_elo = loser["elo"]
    winner_elo = winner["elo"]

    print("Loser elo: " + str(loser_elo))
    print("Winner elo: " + str(winner_elo))
    # Simplified ratings are between 0 and 10

    simplified_loser_elo = 10 ** (loser_elo / 400)
    simplified_winner_elo = 10 ** (winner_elo / 400)

    print("S Loser elo: " + str(simplified_loser_elo))
    print("S Winner elo: " + str(simplified_winner_elo))

    expected_score_loser = (simplified_loser_elo / simplified_loser_elo + simplified_winner_elo)
    expected_score_winner = (simplified_winner_elo / simplified_winner_elo + simplified_loser_elo)

    return abs(expected_score_loser - expected_score_winner)


def calculate_elo_gain(loser, winner):
    data = load_db_file()

    print("calculate_elo_gain loser: " + str(loser))
    print("calculate_elo_gain winner: " + str(winner))
    winner = data[winner]
    loser = data[loser]
    expected_score_winner = calculate_expected_scores(loser, winner)
    # winner_wins = winner["won"]
    # winner_losses = winner["lost"]
    # winner_total_games = winner_wins + winner_losses

    # We only calculate the elo gain for the winner, then invert the result for the loser
    elo_gain = ELO_VARIANCE * (1 - expected_score_winner)

    # elo_gain = ((loser['elo'] + (100 * (winner_wins - winner_losses))) / (winner_total_games + 1)) + 50

    return elo_gain + MINIMUM_ELO_GAIN


def modify_elos(winning_user, loser_user, elo):
    print("Saving elo change to file " + str(elo))
    elo = int(elo)
    data = load_db_file()
    print("Loaded file ")

    if winning_user == loser_user:
        loser_user = TEST_USER

    with open(LEADERBOARD_FILE_NAME, 'w+') as file:
        print("Opened file ")
        print("Winner before " + str(data[winning_user]['elo']))
        data[winning_user]['elo'] = data[winning_user]['elo'] + elo
        data[winning_user]['won'] = data[winning_user]['won'] + 1
        print("Winner now " + str(data[winning_user]))

        print("Loser before " + str(data[loser_user]['elo']))
        data[loser_user]['elo'] = data[loser_user]['elo'] - elo
        data[loser_user]['lost'] = data[loser_user]['lost'] + 1
        print("Loser now " + str(data[winning_user]))

        print(json.dumps(data))
        file.write(json.dumps(data))
        file.close()


def save_user_loss(losing_user, winning_user):
    print("save_user_loss loser: " + str(losing_user))
    print("save_user_loss winner: " + str(winning_user))
    elo = abs(calculate_elo_gain(loser=losing_user, winner=winning_user))
    print("Someone lost " + str(elo) + " points")
    modify_elos(winning_user, losing_user, elo)


def mention(string):
    return '<@' + string + '>'


def handle_loss(losing_user):
    """
        Handle a user accepting his defeat

        losing_user = slack id
    """
    print("User " + losing_user + " accepted a loss")
    if is_in_a_match(losing_user):
        print("he was in a match with")
        winning_user = cancel_match_for(losing_user)
        print("WINNER: " + winning_user)
        save_user_loss(losing_user, winning_user)
        response = mention(winning_user) + ' defeated ' + mention(losing_user)
        if AUTO_SHOW_SCOREBOARD_ON_LOSS:
            response += '\n\n'
            response += print_leaderboard()
        return response
    else:
        print("But he was not in a match, dispatch meme")
        return 'is this :loss: '


def has_active_challenge(user):
    return has_been_challenged(user) or has_challenged_someone(user)


def has_been_challenged(challenged):
    try:
        for item in ACTIVE_CHALLENGES:
            if item.get('challenged') == str(challenged):
                return True
        return False
    except KeyError:
        return False


def has_challenged_someone(challenger):
    try:
        for item in ACTIVE_CHALLENGES:
            if item.get('challenger') == str(challenger):
                return True
        return False
    except KeyError:
        return False


def create_challenge(user1, user2):
    global ACTIVE_CHALLENGES
    user1 = strip_mention(user1)
    user2 = strip_mention(user2)
    ACTIVE_CHALLENGES.append(dict(challenger=user1, challenged=user2))
    # print(str(ACTIVE_CHALLENGES))


def strip_mention(string):
    string = str(string).replace('<@', '')
    string = string.replace('>', '')
    return string


def create_match_between(accepting_user, challenger_user):
    PLAYERS_IN_A_MATCH.append(accepting_user)
    PLAYERS_IN_A_MATCH.append(challenger_user)
    ACTIVE_MATCHES.append([challenger_user, accepting_user])


def delete_challenge(challenge):
    ACTIVE_CHALLENGES.remove(challenge)


def accept_challenge(accepting_user):
    print("Has been challenged: " + accepting_user + ":" + str(has_been_challenged(accepting_user)))
    if has_been_challenged(accepting_user):
        print("Getting challenger of " + accepting_user)
        challenge = get_challenge(challenged=accepting_user, challenger=None)
        challenger_user = challenge['challenger']
        create_match_between(accepting_user, challenger_user)
        delete_challenge(challenge)
        return 'has aceptado el challenge de <@' + challenger_user + '>'
    else:
        print("User " + accepting_user + " has not been challenged" + str(ACTIVE_CHALLENGES))
        return 'No hay challenge para aceptar'


def get_challenge(challenged, challenger):
    if has_been_challenged(challenged):
        for challenge in ACTIVE_CHALLENGES:
            if challenge['challenged'] == challenged:
                return challenge


def init_db():
    if os.path.exists(LEADERBOARD_FILE_NAME) and os.path.getsize(LEADERBOARD_FILE_NAME) > 0:
        pass
    else:
        with open(LEADERBOARD_FILE_NAME, 'w+') as file:
            data = {}
            for user in USERS_LIST:
                data[user.get("id")] = dict(
                    name=user.get("name"),
                    nickname='',
                    elo=BASE_ELO,
                    won=0,
                    lost=0,
                )
            json_string = json.dump(data, file)
            file.close()


def load_db_file():
    print ("Loading file")
    global FILE_CACHE

    if not FILE_CACHE:
        print("Getting file from disk")
        with open(LEADERBOARD_FILE_NAME, 'r') as f:
            data_dict = json.load(f)
            f.close()
            FILE_CACHE = data_dict
            # print(str(data_dict))
            return data_dict
    else:
        print("Returning file from cache")
        # print(str(FILE_CACHE))
        return FILE_CACHE


def format_dict_as_leaderboard(data_dict):
    result = ''
    sorted_results = sorted(data_dict.items(), key=lambda kv: kv[1].get("elo"), reverse=True)
    # print(str(sorted_results))
    i = 1
    for entry in sorted_results:
        if entry[1]["won"] + entry[1]["lost"] != 0:
            print(entry[0], '->', entry[1])
            result += str(i) + '- ' + entry[1]["name"] + ": (Elo: " + str(entry[1]["elo"]) + ', w:' + str(
                entry[1]["won"]) + ', l:' + str(entry[1]["lost"]) + ')\n'
            i += 1

    return 'No leaderboard yet' if result == '' else result


def print_leaderboard():
    print("Trying to load db for leaderboard command")
    data_dict = load_db_file()
    print("Loaded db successfully")
    # print(type(data_dict))
    leaderboard = format_dict_as_leaderboard(data_dict)
    return str(leaderboard)


def init():
    global USER_DATA
    global USERS_LIST
    print("Trying to connect to slack")
    if slack_client.rtm_connect(with_team_state=False):
        print("Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        # pingpongbot_id = slack_client.api_call("auth.test")["user_id"]
        USERS_LIST = slack_client.api_call("users.list")["members"]
        for user in USERS_LIST:
            USER_DATA[user.get("id")] = user.get("name")

        # print(USER_DATA)
        print("Loading db")
        init_db()
    else:
        print("Connection failed. Exception traceback printed above.")
        return None, None


def run():
    while True:
        command, channel, issuing_user = parse_bot_commands(slack_client.rtm_read())
        if command:
            try:
                if command[0] is not None:
                    print('User with id ' + str(issuing_user) + ' called command ' + str(command))
                    handle_command(command, channel, issuing_user)

            except Exception as error:
                print(error)
        time.sleep(RTM_READ_DELAY)


print("Starting bot")
init()
run()
