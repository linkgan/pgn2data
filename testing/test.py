"""
This has been tested using the Lichess API
lichess.org/games/export/nykterstein
lichess.org/games/export/[user_name]?since=1525132800000

===============================
examples of calling:

path = "C:/Users/work/Downloads/"

file1 = path + "lichess_damnsaltythatsport_2021-04-01.pgn"
file2 = path + "lichess_DannyTheDonkey_2021-04-01.pgn"
file3 = path + "lichess_DrDrunkenstein_2021-04-01.pgn"
file4 = path + "lichess_DrNykterstein_2021-04-01.pgn"
file5 = path + "lichess_manwithavan_2021-04-01.pgn"

s = "C:/Users/work/Documents/stockfish/stockfish_20090216_x64_bmi2.exe"

from converter.pgn_data import PGNData

pgn_data = PGNData([file1, file2, file3, file4, file5], "output_99")
#pgn_data = PGNData([file3], "games")
pgn_data.set_engine_path(s)
pgn_data.set_engine_depth(1)
result = pgn_data.export()
result.print_summary()
===============================
"""

import unittest
from converter.board_ref import BoardPieces
import logging
from converter.fen import FenStats
import chess
from common.common import full_range
from converter.pgn_data import PGNData
import os


class BoardRefTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def run_piece_at_square_test(self):
        bp = BoardPieces()
        self.__moving_piece("e2", "e4", bp)
        self.__moving_piece("e7", "e6", bp)
        self.__moving_piece("g1", "f3", bp)

    def __moving_piece(self, from_square, to_square, bp):
        from_before = bp.get_piece_at_square(from_square)
        to_before = bp.get_piece_at_square(to_square)
        bp.track_move(from_square, to_square)
        from_after = bp.get_piece_at_square(from_square)
        to_after = bp.get_piece_at_square(to_square)
        self.assertEqual(bp.get_piece_at_square(to_square), from_before)
        self.assertEqual(bp.get_piece_at_square(from_square), "")
        self.assertNotEqual(to_before, to_after)
        self.assertNotEqual(from_before, from_after)


class FenTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def run_test(self):
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
        fs = FenStats(fen)
        white_total, black_total = fs.get_total_piece_count()
        self.assertEqual(white_total, 16)
        self.assertEqual(black_total, 16)
        capture_white = fs.get_captured_score(chess.WHITE)
        capture_black = fs.get_captured_score(chess.BLACK)
        self.assertEqual(capture_white, 0)
        self.assertEqual(capture_black, 0)
        piece_count = fs.get_piece_count(chess.ROOK, chess.WHITE)
        self.assertEqual(piece_count, 2)
        piece_count = fs.get_piece_count(chess.QUEEN, chess.BLACK)
        self.assertEqual(piece_count, 1)

        valuations = [(8, 31, 0, 0),
                      (7, 7, 0, 0),
                      (0, 0, 0, 0),
                      (1, 1, 0, 0),
                      (0, 0, 0, 0),
                      (0, 0, 0, 0),
                      (0, 0, 8, 8),
                      (0, 0, 8, 31)]

        for r in full_range(1, 8):
            result = fs.get_piece_count_and_value_for_fen_row(r)
            self.assertEqual(result, valuations[r - 1])


class FileCreationTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def run_tests(self):
        self.run_single_file_test()
        self.run_multiple_files_test()

    def run_single_file_test(self):
        folder = os.path.dirname(os.path.realpath(__file__))
        f = folder + "/" + "pgn_test1.pgn"
        o = folder + "/" + "output1"
        pgn_data = PGNData(f, o)
        result = pgn_data.export()
        result.print_summary()
        self.assertTrue(result.is_complete)

    def run_multiple_files_test(self):
        folder = os.path.dirname(os.path.realpath(__file__))
        f1 = folder + "/" + "pgn_test1.pgn"
        f2 = folder + "/" + "pgn_test2.pgn"
        o = folder + "/" + "output2"
        pgn_data = PGNData([f1, f2], o)
        result = pgn_data.export()
        result.print_summary()
        self.assertTrue(result.is_complete)


def board_test():
    test_board_ref = BoardRefTestCase()
    test_board_ref.run_piece_at_square_test()


def fen_stat_tests():
    test_fen = FenTestCase()
    test_fen.run_test()


def file_creation_tests():
    test_creation = FileCreationTestCase()
    test_creation.run_tests()


def run_all_tests():
    """
    This is the main method to run to check the API output
    """
    log = logging.getLogger("pgn2data")
    logging.basicConfig(level=logging.INFO)

    log.info("Start testing")
    board_test()
    fen_stat_tests()
    file_creation_tests()
    log.info("End testing")
