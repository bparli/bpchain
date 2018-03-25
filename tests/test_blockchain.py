from blockchain import Blockchain
import pytest


def test_genesis_blockchain():
    bc = Blockchain()
    assert bc.current_transactions == []
    assert bc.nodes == set()
    assert len(bc.chain) == 1
    last_block = bc.chain[-1]
    assert last_block['index'] == 1
    assert last_block['transactions'] == []
    assert last_block['proof'] == 100
    assert last_block['previous_hash'] == '1'


def test_mining():
    bc = Blockchain()
    bc.mine()
    assert bc.valid_chain(bc.chain)

    bc.last_block['proof'] = 123456
    assert not bc.valid_chain(bc.chain)


def test_transaction():
    bc = Blockchain()
    bc.new_transaction("me", "someone-else", 3)
    assert bc.current_transactions[0]["sender"] == "me"


def test_hash():
    block = {
        'index': 1,
        'timestamp': 1522007611.701286,
        'transactions': [],
        'proof': '1',
        'previous_hash': None,
    }
    bc = Blockchain()
    assert bc.hash(block) == "70b53720b96d4deba891786045ab5626cddbc1f3ecf554224da825d6d7312a87"


def test_register_node():
    bc = Blockchain()
    bc.register_node("http://192.168.0.5:5000")
    assert "192.168.0.5:5000" in bc.nodes
    bc.register_node("192.168.0.5:5001")
    assert "192.168.0.5:5001" in bc.nodes
