"""Unit tests for util.py"""

import unittest
import util


class TestUtilMethods(unittest.TestCase):

    def test_remove_overlap(self):
        # Np overlap
        self.assertEqual(
            util.remove_overlap('Hello', 'World'),
            'World')
        # Simple use cases
        self.assertEqual(
            util.remove_overlap('Hello', 'Hello World'),
            'World')
        self.assertEqual(
            util.remove_overlap('Hello  ', 'Hello World'),
            'World')
        # Strip punctuation and quotes
        self.assertEqual(
            util.remove_overlap('Hello"', 'Hello World'),
            'World')
        self.assertEqual(
            util.remove_overlap('Hello."', 'Hello World'),
            'World')
        self.assertEqual(
            util.remove_overlap('Oh Hello."', 'Hello. World'),
            'World')
        # Retain quotes and punctuation if there was no other overlap
        self.assertEqual(
            util.remove_overlap('Hello."', '"World'),
            '"World')
        self.assertEqual(
            util.remove_overlap('Hello."', '."World'),
            '."World')
        # ... but still strip whitespace
        self.assertEqual(
            util.remove_overlap('Hello."', ' ."World'),
            '."World')

    def test_last_sentences(self):
        paragraph = 'First. Second.\n\nThird'
        self.assertEqual(
            util.last_sentences(paragraph, 1),
            'Third.')
        self.assertEqual(
            util.last_sentences(paragraph + '.', 1),
            'Third.')
        self.assertEqual(
            util.last_sentences(paragraph + '.', 2),
            'Second. Third.')
        self.assertEqual(
            util.last_sentences(paragraph, 3),
            'First. Second. Third.')
        self.assertEqual(
            util.last_sentences(paragraph, 4),
            'First. Second. Third.')
        self.assertEqual(
            util.last_sentences('', 4),
            '')
