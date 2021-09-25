import csv
import logging
import ntpath
import queue
import uuid
from threading import Thread
import io

import chess
import chess.pgn
import chess.engine
import pandas as pd

import sys
sys.path.append("../../pgn2data")

from pgn2data.common.log_time import get_time_stamp
from pgn2data.converter.fen import FenStats
from pgn2data.converter.headers import file_headers_game, file_headers_moves, file_headers_stockfish
from pgn2data.converter.move_assessment import move_assessment
from pgn2data.converter.gamePlayerMove import GamePlayerMove

log = logging.getLogger("pgn2data - process")
logging.basicConfig(level=logging.INFO)

import sqlite3 as sql


class PlayerMove:
    """
    data class to hold details of each move
    move = Move object from python chess library
    notation = is algebraic notation of the move
    """

    def __init__(self, move, notation):
        self.move = move
        self.notation = notation
        self.__piece = ""

    def get_from_square(self):
        return str(self.move)[0:2] if self.__is_valid_move() else ""

    def get_to_square(self):
        return str(self.move)[2:4] if self.__is_valid_move() else ""

    def __is_valid_move(self):
        return len(str(self.move)) >= 4

    def set_piece(self, piece):
        self.__piece = piece

    def get_piece(self):
        return self.__piece


class Game:
    """
        This is a new class.
        This is a game object that is a collection of GamePlayerMove
    """
    def __init__(self, game, game_id, move_list=None):
        self.game = game ###Chess.game object
        self.game_id = game_id
        self.move_list = move_list

    def get_game(self):
        return self.game

class Process:
    """
    Handles the pgn to data conversion
    """

    def __init__(self, pgn_file, file_games, file_moves, engine_path, engine_depth, source, game_id=None):
        self.pgn_file = pgn_file
        self.file_games = file_games
        self.file_moves = file_moves
        self.engine_path = engine_path
        self.engine_depth = engine_depth
        self.source = source
        self.game_id = game_id
        self.con = sql.connect("data/moves_f.db")

        log.info("**** Using new Process file ****")

    # def parse_pgn(self):

    def parse_file(self, add_headers_flag=True):
        """
        processes on pgn file and then exports game information
        into the game csv file, and the moves into the moves csv file
        """

        if(self.source == 'chess.com'):
            log.info("Processing pgn string from Chess.com api: {} ".format(self.game_id))
            pgn = io.StringIO(self.pgn_file)

        else:
            log.info("Processing file:{} [NEED TO UPDATE THIS FILE PROCESSING METHOD]".format(self.pgn_file))
            pgn = open(self.pgn_file)

        engine = None
        if self.engine_path is not None:
            engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)

        q = queue.Queue(maxsize=0)
        worker = Thread(target=self.__process_move_queue, args=(q,))
        worker.setDaemon(True)
        worker.start()

        move_writer = csv.writer(self.file_moves, delimiter=',')
        if add_headers_flag:
            headers = file_headers_moves
            if engine is not None:
                headers.extend(file_headers_stockfish)
            move_writer.writerow(headers)

        game_writer = csv.writer(self.file_games, delimiter=',')
        if add_headers_flag:
            game_writer.writerow(file_headers_game)

        order = 1
        while True:
            game_id = -1
            if self.source == 'chess.com':
                game_id = self.game_id
            else:
                game_id = str(uuid.uuid4())

            game = Game(chess.pgn.read_game(pgn), game_id)

            if game.get_game() is None:
                break  # end of file

            ### Create Game object to process

            ### Update to SQLite DB
            game_writer.writerow(self.__get_game_row_data(game.game, game.game_id, order, self.pgn_file))


            q.put((game.game_id, game.game, move_writer, engine, self.engine_depth))
            order += 1

        q.join()

        if engine is not None:
            engine.quit()

    def __process_move_queue(self, q):
        """
        process moves in the blocking queue as they are added
        """
        while True:
            item = q.get()
            # game_id | game | move_writer | engine | engine_depth
            self.__process_move(item[0], item[1], item[2], item[3], item[4])
            q.task_done()

    def __move_to_db(self, move):
        """
        Insert data from processed move into table
        """
        table_name = 'moves_f'
        cur = self.con.cursor()
        cur.execute(f'''
            INSERT INTO {table_name}

        ''')

    def __process_move(self, game_id, game, moves_writer, engine, depth):
        """
        process all the moves in a game
        """
        board = game.board()
        order_number = 1
        players_order_number = 1
        sequence = ""

        # track stockfish evaluation
        white_eval = 0
        black_eval = 0

        for move in game.mainline_moves():
            notation = board.san(move)
            board.push(move)
            player_move = PlayerMove(move, notation)

            # this gets the name of the piece that was moved
            index = chess.SQUARE_NAMES.index(player_move.get_to_square())
            p = board.piece_at(chess.SQUARES[index])

            player_move.set_piece(str(p))
            sequence += ("|" if len(sequence) > 0 else "") + str(notation)

            # output the data about the move to the file
            row_data, prev_eval, is_white, moveObj = self.__get_move_row_data(player_move, board, game_id, game, order_number,
                                                                     players_order_number, sequence, engine, depth,
                                                                     white_eval, black_eval)
            moves_writer.writerow(row_data)
            log.info("TO DO: write moveObj ({}) to a SQLite DB".format(type(moveObj.board_data.values())))


            # this is tracking the move numbers in the game
            players_order_number += 1 if (order_number % 2) == 0 else 0
            order_number += 1

            # this is tracking what the previous evaluation is for each move
            # so it can be inserted alongside the current row
            white_eval = prev_eval if is_white else white_eval
            black_eval = prev_eval if not is_white else black_eval

    def __get_game_row_data(self, game, game_id, order, file_name):
        """
        takes a "game" object and converts it into a list with the data for each column
        """

        winner = self.__get_winner(game)

        loser = game.headers["White"] if winner == game.headers["Black"] else (
            game.headers["Black"] if winner == game.headers["White"] else winner)
        winner_elo = game.headers["WhiteElo"] if winner == game.headers["White"] else (
            game.headers["BlackElo"] if winner == game.headers["Black"] else "")
        loser_elo = game.headers["WhiteElo"] if winner == game.headers["Black"] else (
            game.headers["BlackElo"] if winner == game.headers["White"] else "")
        winner_loser_elo_diff = 0 if not (str(winner_elo).isnumeric() and str(loser_elo).isnumeric()) else int(
            winner_elo) - int(loser_elo)

        log.info("TO DO: Need to implement game summary stats in the game row data")
        return [game_id, order,
                game.headers["Event"] if "Event" in game.headers else "",
                game.headers["Site"] if "Site" in game.headers else "",
                game.headers["Date"] if "Date" in game.headers else "",
                game.headers["Round"] if "Round" in game.headers else "",
                game.headers["White"] if "White" in game.headers else "",
                game.headers["Black"] if "Black" in game.headers else "",
                game.headers["Result"] if "Result" in game.headers else "",
                game.headers["WhiteElo"] if "WhiteElo" in game.headers else "",
                game.headers["WhiteRatingDiff"] if "WhiteRatingDiff" in game.headers else "",
                game.headers["BlackElo"] if "BlackElo" in game.headers else "",
                game.headers["BlackRatingDiff"] if "BlackRatingDiff" in game.headers else "",
                game.headers["WhiteTitle"] if "WhiteTitle" in game.headers else "",
                game.headers["BlackTitle"] if "BlackTitle" in game.headers else "",
                winner,
                winner_elo,
                loser,
                loser_elo,
                winner_loser_elo_diff,
                game.headers["ECO"] if "ECO" in game.headers else "",
                game.headers["Termination"] if "Termination" in game.headers else "",
                game.headers["TimeControl"] if "TimeControl" in game.headers else "",
                game.headers["UTCDate"] if "UTCDate" in game.headers else "",
                game.headers["UTCTime"] if "UTCTime" in game.headers else "",
                game.headers["Variant"] if "Variant" in game.headers else "",
                game.headers["PlyCount"] if "PlyCount" in game.headers else "",
                get_time_stamp(), ntpath.basename(file_name)]

    __fen_row_counts_and_valuation_dict = {}

    def __get_move_row_data(self, player_move, board, game_id, game, order_number, players_order_number, sequence,
                            engine, depth, white_eval, black_eval):
        """
        process each move in a game
        """

        '''
            Initialize a GamePlayerMove object to capture all relevant information about each parsed move
        '''


        fen_stats = FenStats(board.board_fen())
        white_count, black_count = fen_stats.get_total_piece_count()

        if fen_stats.fen_position in self.__fen_row_counts_and_valuation_dict:
            fen_row_valuations = self.__fen_row_counts_and_valuation_dict[fen_stats.fen_position]
        else:
            fen_row_valuations = fen_stats.get_fen_row_counts_and_valuation()
            self.__fen_row_counts_and_valuation_dict[fen_stats.fen_position] = fen_row_valuations

        is_white_move = not self.__is_number_even(order_number)

        player_name = game.headers["White"] if is_white_move else game.headers["Black"]
        player_colour = "White" if is_white_move else "Black"

        # this calculates engine evaluation but only an engine has been specified
        evaluation = 0
        if engine is not None:
            evaluation = self.__get_evaluation_from_board(board, depth, engine, is_white_move)

        data = [game_id,
                order_number,
                players_order_number,
                player_name,
                player_move.notation,
                player_move.move,
                player_move.get_from_square(),
                player_move.get_to_square(),
                player_move.get_piece().upper(),
                player_colour,
                board.board_fen(),
                1 if board.is_check() else 0,
                1 if board.is_checkmate() else 0,
                1 if board.is_fifty_moves() else 0,
                1 if board.is_fivefold_repetition() else 0,
                1 if board.is_game_over() else 0,
                1 if board.is_insufficient_material() else 0,
                white_count,
                black_count,
                fen_stats.get_piece_count(chess.PAWN, chess.WHITE),
                fen_stats.get_piece_count(chess.PAWN, chess.BLACK),
                fen_stats.get_piece_count(chess.QUEEN, chess.WHITE),
                fen_stats.get_piece_count(chess.QUEEN, chess.BLACK),
                fen_stats.get_piece_count(chess.BISHOP, chess.WHITE),
                fen_stats.get_piece_count(chess.BISHOP, chess.BLACK),
                fen_stats.get_piece_count(chess.KNIGHT, chess.WHITE),
                fen_stats.get_piece_count(chess.KNIGHT, chess.BLACK),
                fen_stats.get_piece_count(chess.ROOK, chess.WHITE),
                fen_stats.get_piece_count(chess.ROOK, chess.BLACK),
                fen_stats.get_captured_score(chess.WHITE),
                fen_stats.get_captured_score(chess.BLACK),
                fen_row_valuations[0][0], fen_row_valuations[1][0], fen_row_valuations[2][0], fen_row_valuations[3][0],
                fen_row_valuations[4][0], fen_row_valuations[5][0], fen_row_valuations[6][0], fen_row_valuations[7][0],
                fen_row_valuations[0][1], fen_row_valuations[1][1], fen_row_valuations[2][1], fen_row_valuations[3][1],
                fen_row_valuations[4][1], fen_row_valuations[5][1], fen_row_valuations[6][1], fen_row_valuations[7][1],
                fen_row_valuations[0][2], fen_row_valuations[1][2], fen_row_valuations[2][2], fen_row_valuations[3][2],
                fen_row_valuations[4][2], fen_row_valuations[5][2], fen_row_valuations[6][2], fen_row_valuations[7][2],
                fen_row_valuations[0][3], fen_row_valuations[1][3], fen_row_valuations[2][3], fen_row_valuations[3][3],
                fen_row_valuations[4][3], fen_row_valuations[5][3], fen_row_valuations[6][3], fen_row_valuations[7][3],
                sequence]

        move = GamePlayerMove(player_move, game_id, order_number)
        move.set_board_data(dict(zip(file_headers_moves, data)))

        if engine is not None:
            if isinstance(evaluation, int) and isinstance(white_eval, int) and isinstance(black_eval, int):
                eng_data = []

                prev_value = white_eval if is_white_move else black_eval
                diff_value = (float(evaluation) - float(prev_value))/100.0

                eng_data.append(evaluation / 100.0)
                eng_data.append(prev_value / 100.0)
                eng_data.append(diff_value)
                eng_data.append(depth)

                # Added Move move_assessment, checks if the difference between engine best move and current move is of blunder or not
                for key, value in move_assessment.items():
                    if diff_value >= value['start'] and diff_value < value['end']:
                        eng_data.append(key)
                        break

                move.set_engine_data(dict(zip(file_headers_stockfish, eng_data)))
                data = data+eng_data

        ### Initialize move object and store all the relevant data in this object

        return data, evaluation, is_white_move, move

    @staticmethod
    def __get_evaluation_from_board(board, depth, engine, is_white_move):
        # this wrapped in a function because engline.analyse is not able to
        # parse the board object without errors
        evaluation = 0
        try:
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            pov_score = info["score"]
            evaluation = pov_score.white().score() if is_white_move else pov_score.black().score()
        except Exception as ex:
            log.error(ex)
        return evaluation

    @staticmethod
    def __is_number_even(number):
        return number % 2 == 0

    @staticmethod
    def __get_winner(game):
        info = game.headers
        if "White" in info and "Black" in info and "Result" in info:
            if game.headers["Result"] == "1/2-1/2":
                return "draw"
            return game.headers["White"] if game.headers["Result"] == "1-0" else game.headers["Black"]
        else:
            return ""
