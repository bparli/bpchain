from flask import Flask, jsonify, request
from argparse import ArgumentParser
from blockchain import Blockchain
import threading
import requests
import logging

# Instantiate our Node
app = Flask(__name__)

# Instantiate the Blockchain
blockchain = Blockchain()


@app.route('/mine', methods=['GET'])
def mine():
    block = blockchain.mine()

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Check for required fields
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new transaction
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: please supply a valid list of nodes", 400

    for node in nodes:
        try:
            blockchain.register_node(node)
        except ValueError as e:
            logging.error("Error registering node: %s error: %s", node, e)

    response = {
        'message': 'Current blockchain nodes',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/peers', methods=['GET'])
def share_peers():
    response = {
        'message': 'Current blockchain nodes',
        'nodes': list(blockchain.nodes),
    }
    return jsonify(response), 200


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


def register_with_neighbor(neighbor, address):
    payload = {'nodes': [address]}
    try:
        requests.post(f"{neighbor}/nodes/register", json=payload)
    except requests.exceptions.RequestException as e:
        logging.error("Error connecting to neighbor %s : %s", neighbor, e)


def sync_with_peers(seeds, address):
    neighbours = seeds.split(",")
    for neighbor in neighbours:
        try:
            blockchain.register_node(neighbor)
        except ValueError as e:
            logging.error("Error registering node: %s error: %s", neighbor, e)
            continue
        register_with_neighbor(neighbor, address)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-s', '--seeds', type=str, help='Initial neighboring blockchain nodes')
    parser.add_argument('-a', '--address', type=str, default="http://127.0.0.1:5000", help='Local address')
    args = parser.parse_args()
    blockchain.address = args.address.split("//")[1]
    if args.seeds is not None:
        sync_with_peers(args.seeds, args.address)
    thr = threading.Thread(target=blockchain.query_nodes)
    thr.daemon = True
    thr.start()

    app.run(host='0.0.0.0', port=int(args.address.split(":")[2]))
