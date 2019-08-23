import time
from random import randrange
import json
import os
import sys
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient(os.environ['BOT_TOKEN'])
# bot's user ID in Slack: value is assigned after the bot starts up
pingpongbot_id = None


# @slack_client.RTMClient.run_on(event="message")

class PingPongBot:
    def __init__(self):
        self.ALLOWED_CHANNELS = ["CMM7PDSUX"]
        # self.TEST_CHANNEL = "CMM7PDSUX"
        self.USERS_LIST = []
        self.USER_DATA = {}
        self.ACTIVE_CHALLENGES = []
        self.ACTIVE_MATCHES = []
        self.PLAYERS_IN_A_MATCH = []
        self.FILE_CACHE = {}
        self.BASE_ELO = 0
        self.ELO_VARIANCE = 32
        self.TEST_USER = 'U8C1J0VFA'
        self.LEADERBOARD_FILE_NAME = 'leaderboard.json'
        self.AUTO_SHOW_SCOREBOARD_ON_LOSS = True
        self.MINIMUM_ELO_GAIN = 10
        self.DEBUG_MODE = True
        self.TAUNTS_LIST = ["No sabes lo que {0} dijo de tu vieja, {1}!",
                            "Lo que te dijo {0}! En mi barrio matan por menos, {1}",
                            "{0} dijo que sos re mediocre en el ping pong, {1}",
                            "{0} dijo que te apesta el aliento, {1}",
                            "{0} dijo que si le pasaras una cartita que dice 'Queres ser mi amigo?' marcaría la casilla de 'No'! Hacete respetar, {1}",
                            "{0} dijo que {1} va al baño y no tira la cadena",
                            "{0} dijo que te gusta PHP, {1}"]

        self.USER_DATA
        # global self.USERS_LIST
        print("Trying to connect to slack")
        if slack_client.rtm_connect():
            print("Bot connected and running!")
            self.USERS_LIST = slack_client.api_call("users.list")["members"]
            for user in self.USERS_LIST:
                self.USER_DATA[user.get("id")] = user.get("name")

            # print(self.USER_DATA)
            print("Loading db")
            self.init_db()
        else:
            print("Connection failed. Exception traceback printed above.")
            return None, None

    def parse_bot_commands(self, event):
        """
            Parses a list of events coming from the Slack RTM API to find bot commands.
            If a bot command is found, this function returns a tuple of command and channel.
            If its not found, then this function returns None, None.
        """
        # Get the id of the Slack user associated with the incoming event
        print("Parsing event " + str(event))
        channel = event["channel"]

        if event["type"] == "message" and "subtype" not in event and self.bot_was_mentioned(event["text"]):
            message = self.parse_mention(event["text"])
            # print(event)
            return message, channel, event["user"]

        return None, None, None

    @staticmethod
    def parse_mention(message_text):
        """
            Finds a message stating with pp
        """
        matches = None, None
        if str(message_text).startswith("pp "):
            matches = message_text.split()

        return (matches[1], matches[2:]) if matches else (None, None)

    def cancel_match_for(self, user_to_remove):
        """
        Cancels the match that user_to_remove is a part of, and returns the other player
        :param user_to_remove:  -- The userId to remove from the pool of matches
        :return: -- The userId of the other player involved
        """

        print("Removing player " + user_to_remove + "from " + str(self.PLAYERS_IN_A_MATCH))
        self.PLAYERS_IN_A_MATCH.remove(user_to_remove)
        other_player = None
        print("ACTIVE MATCHES " + str(self.ACTIVE_MATCHES))
        for match in self.ACTIVE_MATCHES:
            for each_user in match:
                if each_user == user_to_remove:
                    other_player = self.get_other_user(user_to_remove, match)
                    print("Removing player " + other_player + " from " + str(self.PLAYERS_IN_A_MATCH))
                    self.PLAYERS_IN_A_MATCH.remove(other_player)
                    print("PLAYERS IN A MATCH NOW " + str(self.PLAYERS_IN_A_MATCH))
                    self.ACTIVE_MATCHES.remove(match)
                    print("ACTIVE MATCHES NOW " + str(self.ACTIVE_MATCHES))

        return other_player

    def cancel_challenge_for(self, cancelling_user):
        """
        Cancels any present challenges for this user

        :param cancelling_user:
        :return:
        """
        for challenge in self.ACTIVE_CHALLENGES:
            if challenge["challenged"] == cancelling_user or challenge["challenger"] == cancelling_user:
                print("Found a challenge to cancel: " + str(challenge))
                self.ACTIVE_CHALLENGES.remove(challenge)
                return

    def cancel_challenge_or_match(self, cancelling_user):
        if self.is_in_a_match(cancelling_user):
            self.cancel_match_for(cancelling_user)
            return "Match cancelled"

        if self.has_active_challenge(cancelling_user):
            self.cancel_challenge_for(cancelling_user)
            return "Challenge cancelled"

        return 'Nothing to cancel'

    def random_taunt(self, taunting_user, mentioned_user):
        taunt_id = randrange(len(self.TAUNTS_LIST))
        print("Taunt id " + str(taunt_id) + " Taunt list length " + str(len(self.TAUNTS_LIST)))
        return self.TAUNTS_LIST[taunt_id].format(taunting_user, mentioned_user)

    def handle_command(self, event):
        """
            Executes bot command if the command is known
        """
        command, channel, user = self.parse_bot_commands(event)
        if command is None:
            return

        default_response = ':why-not: DONT UNDERTIENDO COMANDO!! :why-not:'
        response = None
        action = command[0]

        params = command[1]

        if action == 'test':
            response = "ITS ALIVE!"
        if action == 'challenge':
            response = self.handle_challenge(user, params)
        if action == 'lost':
            response = self.handle_loss(user)
        if action == 'accept':
            response = self.accept_challenge(user)
        if action == 'leaderboard':
            response = self.print_leaderboard()
        if action == 'cancel':
            response = self.cancel_challenge_or_match(user)
        if action == 'acceptAs' and self.DEBUG_MODE:
            response = self.accept_challenge(self.strip_mention(params[0]))
        if action == 'taunt':
            response = self.random_taunt(self.mention(user), params[0])

        # Sends the response back to the channel
        slack_client.api_call(
            "chat.postMessage",
            channel=channel,
            text=response or default_response
        )

        return response or default_response

    def is_in_a_match(self, enemy_user):
        return enemy_user in self.PLAYERS_IN_A_MATCH

    def handle_challenge(self, user, params):
        enemy_user = params[0]
        if self.has_active_challenge(user):
            return 'You have a pending challenge!'

        if self.has_active_challenge(enemy_user):
            return str(self.USER_DATA[enemy_user] + ' has an active challenge ')

        if self.is_in_a_match(user):
            return self.USER_DATA[user] + " is in a match"

        if self.is_in_a_match(enemy_user):
            return self.USER_DATA[enemy_user] + " is in a match"

        self.create_challenge(user, enemy_user)

        return 'Te desafiaron a un duelo a muerte con cuchillos, ' + enemy_user + '!'

    def get_other_user(self, user_to_remove, match):
        return match[1] if match[0] == user_to_remove else match[0]

    def calculate_expected_scores(self, loser, winner):
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

    def calculate_elo_gain(self, loser, winner):
        data = self.load_db_file()

        print("calculate_elo_gain loser: " + str(loser))
        print("calculate_elo_gain winner: " + str(winner))
        winner = data[winner]
        loser = data[loser]
        expected_score_winner = self.calculate_expected_scores(loser, winner)
        # winner_wins = winner["won"]
        # winner_losses = winner["lost"]
        # winner_total_games = winner_wins + winner_losses

        # We only calculate the elo gain for the winner, then invert the result for the loser
        elo_gain = self.ELO_VARIANCE * (1 - expected_score_winner)

        # elo_gain = ((loser['elo'] + (100 * (winner_wins - winner_losses))) / (winner_total_games + 1)) + 50
        # print ("ELO GAIN : " + str(elo_gain))

        return max(elo_gain, self.MINIMUM_ELO_GAIN)

    def modify_elos(self, winning_user, loser_user, elo):
        print("Saving elo change to file " + str(elo))
        elo = int(elo)
        data = self.load_db_file()
        print("Loaded file ")

        if winning_user == loser_user:
            loser_user = self.TEST_USER

        with open(self.LEADERBOARD_FILE_NAME, 'w+') as file:
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

    def save_user_loss(self, losing_user, winning_user):
        print("save_user_loss loser: " + str(losing_user))
        print("save_user_loss winner: " + str(winning_user))
        elo = abs(self.calculate_elo_gain(loser=losing_user, winner=winning_user))
        print("Someone lost " + str(elo) + " points")
        self.modify_elos(winning_user, losing_user, elo)

    def mention(self, string):
        return '<@' + string + '>'

    def handle_loss(self, losing_user):
        """
            Handle a user accepting his defeat

            losing_user = slack id
        """
        print("User " + losing_user + " accepted a loss")
        if self.is_in_a_match(losing_user):
            print("he was in a match with")
            winning_user = self.cancel_match_for(losing_user)
            print("WINNER: " + winning_user)
            self.save_user_loss(losing_user, winning_user)
            response = self.mention(winning_user) + ' defeated ' + self.mention(losing_user)
            if self.AUTO_SHOW_SCOREBOARD_ON_LOSS:
                response += '\n\n'
                response += self.print_leaderboard()
            return response
        else:
            print("But he was not in a match, dispatch meme")
            return 'is this :loss: '

    def has_active_challenge(self, user):
        return self.has_been_challenged(user) or self.has_challenged_someone(user)

    def has_been_challenged(self, challenged):
        try:
            for item in self.ACTIVE_CHALLENGES:
                if item.get('challenged') == str(challenged):
                    return True
            return False
        except KeyError:
            return False

    def has_challenged_someone(self, challenger):
        try:
            for item in self.ACTIVE_CHALLENGES:
                if item.get('challenger') == str(challenger):
                    return True
            return False
        except KeyError:
            return False

    def create_challenge(self, user1, user2):

        user1 = self.strip_mention(user1)
        user2 = self.strip_mention(user2)
        self.ACTIVE_CHALLENGES.append(dict(challenger=user1, challenged=user2))
        # print(str(self.ACTIVE_CHALLENGES))

    def strip_mention(self, string):
        string = str(string).replace('<@', '')
        string = string.replace('>', '')
        return string

    def create_match_between(self, accepting_user, challenger_user):
        self.PLAYERS_IN_A_MATCH.append(accepting_user)
        self.PLAYERS_IN_A_MATCH.append(challenger_user)
        self.ACTIVE_MATCHES.append([challenger_user, accepting_user])

    def delete_challenge(self, challenge):
        self.ACTIVE_CHALLENGES.remove(challenge)

    def accept_challenge(self, accepting_user):
        print("Has been challenged: " + accepting_user + ":" + str(self.has_been_challenged(accepting_user)))
        if self.has_been_challenged(accepting_user):
            print("Getting challenger of " + accepting_user)
            challenge = self.get_challenge(challenged=accepting_user, challenger=None)
            challenger_user = challenge['challenger']
            self.create_match_between(accepting_user, challenger_user)
            self.delete_challenge(challenge)
            return 'has aceptado el challenge de <@' + challenger_user + '>'
        else:
            print("User " + accepting_user + " has not been challenged" + str(self.ACTIVE_CHALLENGES))
            return 'No hay challenge para aceptar'

    def get_challenge(self, challenged, challenger):
        if self.has_been_challenged(challenged):
            for challenge in self.ACTIVE_CHALLENGES:
                if challenge['challenged'] == challenged:
                    return challenge

    def init_db(self):
        if os.path.exists(self.LEADERBOARD_FILE_NAME) and os.path.getsize(self.LEADERBOARD_FILE_NAME) > 0:
            pass
        else:
            with open(self.LEADERBOARD_FILE_NAME, 'w+') as file:
                data = {}
                for user in self.USERS_LIST:
                    data[user.get("id")] = dict(
                        name=user.get("name"),
                        nickname='',
                        elo=self.BASE_ELO,
                        won=0,
                        lost=0,
                    )
                json_string = json.dump(data, file)
                file.close()

    def load_db_file(self):
        print ("Loading file")
        # global self.FILE_CACHE

        if not self.FILE_CACHE:
            print("Getting file from disk")
            with open(self.LEADERBOARD_FILE_NAME, 'r') as f:
                data_dict = json.load(f)
                f.close()
                self.FILE_CACHE = data_dict
                # print(str(data_dict))
                return data_dict
        else:
            print("Returning file from cache")
            # print(str(self.FILE_CACHE))
            return self.FILE_CACHE

    def format_dict_as_leaderboard(self, data_dict):
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

    def print_leaderboard(self):
        print("Trying to load db for leaderboard command")
        data_dict = self.load_db_file()
        print("Loaded db successfully")
        # print(type(data_dict))
        leaderboard = self.format_dict_as_leaderboard(data_dict)
        return str(leaderboard)



    def bot_was_mentioned(self, param):
        return True if str(param).startswith("pp ") else False
