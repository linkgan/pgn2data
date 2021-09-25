import logging

log = logging.getLogger("pgn2data - GamePlayerMove")
logging.basicConfig(level=logging.INFO)

class GamePlayerMove:
    """
        This is a new class
        Extends PlayerMove to include metadata of each move for analytic purposes
        Unique to Each Game_id
    """

    def __init__(self, player_move, game_id, order_number, data = None):
        self.player_move = player_move
        self.game_id = game_id
        self.order_number = order_number
        self.board_data = data
        self.engine_data = None

    def set_board_data(self, data):
        self.board_data = data
    def set_engine_data(self, data):
        self.engine_data = data

    def merge_data(self, data):
        if(isinstance(self.data, dict) and isinstance(data, dict)):
            # print(self.data)
            old_dict = self.data.copy()
            old_dict.update(data)
            self.data = old_dict
            # log.info("Checking merged data: Data size {}".format(len(self.data)))
        else:
            log.error("Cannot merge non-dict data")
