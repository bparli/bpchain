import hashlib
import json
from time import time, sleep
from urllib.parse import urlparse
import requests
import logging
from threading import Lock, Thread
from uuid import uuid4

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')


class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.transactions_per_block = 5
        self.nodes = set()
        self.nodes_mutex = Lock()
        self.address = ""

        # Create the genesis Block
        self.new_block(previous_hash='1', proof=100)

    def proof_of_work(self, last_block):
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(pp') contains leading 4 zeroes
         - Where p is the previous proof, and p' is the new proof

        :param last_block: <dict> last Block
        :return: <int>
        """

        last_proof = last_block['proof']
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1

        return proof

    def mine(self):
        """
        Compute the proof, append a final transaction
        and mine a new Block in the chain
        :return: <dict> New Block
        """
        # We run the proof of work algorithm to get the next proof...
        last_block = self.last_block
        proof = self.proof_of_work(last_block)

        # We must receive a reward for finding the proof.
        # The sender is "0" to signify that this node has mined a new coin.
        self.current_transactions.append({
            'sender': "0",
            'recipient': node_identifier,
            'amount': 1,
        })

        # Since we have a new block, trigger peers to
        # resolve potential chain conflicts
        thr = Thread(target=self.force_resolve)
        thr.daemon = True
        thr.start()

        # Forge the new Block by adding it to the chain
        previous_hash = self.hash(last_block)

        return self.new_block(proof, previous_hash)

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        """
        Validates the Proof: Does hash contain 4 leading zeroes?
        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :return: <bool> True if correct, False if not.
        """
        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def force_resolve(self):
        for node in self.nodes:
            requests.get(f"http://{node}/nodes/resolve")

    def new_block(self, proof, previous_hash):
        """
        Create a new Block in the Blockchain
        :param proof: <int> The proof given by the Proof of Work algorithm
        :param previous_hash: (Optional) <str> Hash of previous Block
        :return: <dict> New Block
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block
        :param sender: <str> Address of the Sender
        :param recipient: <str> Address of the Recipient
        :param amount: <int> Amount
        :return: <int> The index of the Block that will hold this transaction
        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        if len(self.current_transactions) >= self.transactions_per_block:
            self.mine()
            return self.last_block['index']
        else:
            return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block
        :param block: <dict> Block
        :return: <str>
        """

        # We must make sure that the Dictionary is Ordered,
        # or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        # Returns the last Block in the chain
        return self.chain[-1]

    def register_node(self, address):
        """
        Add a new node to the list of nodes
        :param address: <str> Address of node. Eg. 'http://192.168.0.5:5000'
        :return: None
        """
        self.nodes_mutex.acquire()
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)
        elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
            self.nodes.add(parsed_url.path)
        else:
            self.nodes_mutex.release()
            raise ValueError('Invalid URL')
        self.nodes_mutex.release()

    def query_nodes(self):
        """
        Query nodes for its known nodes and add to set.
        """
        while True:
            found_nodes = set()
            for node in self.nodes:
                try:
                    response = requests.get(f"http://{node}/nodes/peers")
                    if response.status_code == 200:
                        for neighbor in response.json()['nodes']:
                            found_nodes.add(neighbor)
                except requests.exceptions.ConnectionError as e:
                    logging.error("Error connecting to peer %s : %s", node, e)
            for node in found_nodes:
                try:
                    self.register_node(node)
                except ValueError as e:
                    logging.error("Error adding new node %s : %s",
                                  node, e)
            sleep(30)

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid
        :param chain: <list> A blockchain
        :return: <bool> True if valid, False if not
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof'],
                                    block['previous_hash']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is our consensus algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.
        :return: True if our chain was replaced, False if not
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        peers = (node for node in neighbours if node != self.address)
        for node in peers:
            response = requests.get(f"http://{node}/chain")

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new,
        # valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False
