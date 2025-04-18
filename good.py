from flask import Flask, render_template_string, request, redirect, session, url_for
import socket
import threading
import json

app = Flask(__name__)
app.secret_key = 'change_this_secret_key'

# Configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 12345
ADMIN_PASSWORD = 'loveletter'

# Shared game state
clients = {}

# HTML Templates
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Connexion Love Letter</title></head>
<body>
<h2>Connexion</h2>
<form method="post">
    Mot de passe : <input type="password" name="password"><br>
    Nom du joueur : <input type="text" name="username">
    <input type="submit" value="Entrer">
</form>
</body>
</html>
"""

GAME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Love Letter Web</title>
    <style>
        body { font-family: sans-serif; }
        .card-list { margin-bottom: 1em; }
        .card-list strong { display: block; margin-top: 1em; }
    </style>
</head>
<body>
<h2>Bienvenue {{ username }}</h2>
<p><strong>Joueurs :</strong> {{ players }}</p>
<p><strong>Ta main :</strong> {{ hand }}</p>
<form method="post" action="/play">
    <p>
        Choisis une carte :
        <select name="card">
            {% for c in hand %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
        </select>
    </p>
    <p>
        Cible (optionnelle) :
        <input type="text" name="target" placeholder="Nom du joueur">
    </p>
    <p>
        Deviner (si Garde) :
        <input type="text" name="guess" placeholder="Nom de la carte">
    </p>
    <button type="submit">Jouer</button>
</form>

<h3>Historique par joueur</h3>
<div class="card-list">
{% for joueur, cartes in player_history.items() %}
    <strong>{{ joueur }}</strong>: {{ ", ".join(cartes) if cartes else '---' }}<br>
{% endfor %}
</div>

<h3>Messages</h3>
<ul>
{% for m in messages %}
    <li>{{ m }}</li>
{% endfor %}
</ul>

<form method="post" action="/ready">
    <button type="submit">Je suis prêt !</button>
</form>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            username = request.form.get('username')
            session['auth'] = True
            session['username'] = username
            # Create a TCP connection for the user
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.send((json.dumps({"type": "name", "name": username}) + '\n').encode())
            clients[username] = {
                'sock': sock,
                'buffer': '',
                'hand': [],
                'players': [],
                'history': [],
                'messages': []
            }
            threading.Thread(target=receive_from_server, args=(username,), daemon=True).start()
            return redirect(url_for('game'))
    return LOGIN_HTML

@app.route('/game')
def game():
    if not session.get('auth') or session['username'] not in clients:
        return redirect(url_for('login'))
    client = clients[session['username']]
    player_history = {}
    for entry in client['history']:
        joueur = entry['player']
        carte = entry['card']
        player_history.setdefault(joueur, []).append(carte)
    return render_template_string(GAME_HTML,
        username=session['username'],
        hand=client['hand'],
        players=client['players'],
        messages=client['messages'][-10:],
        player_history=player_history
    )

@app.route('/play', methods=['POST'])
def play():
    username = session.get('username')
    if not username or username not in clients:
        return redirect(url_for('login'))
    card = request.form.get('card')
    target = request.form.get('target')
    guess = request.form.get('guess')
    client = clients[username]
    msg = {
        'type': 'play',
        'card': card,
        'target': client['players'].index(target) if target in client['players'] else None,
        'guess': guess or None
    }
    client['sock'].send((json.dumps(msg) + '\n').encode())
    return redirect(url_for('game'))

@app.route('/ready', methods=['POST'])
def ready():
    username = session.get('username')
    if not username or username not in clients:
        return redirect(url_for('login'))
    client = clients[username]
    client['sock'].send((json.dumps({"type": "ready"}) + '\n').encode())
    return redirect(url_for('game'))

def receive_from_server(username):
    client = clients[username]
    sock = client['sock']
    buffer = ""
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                break
            buffer += data.decode()
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    msg = json.loads(line.strip())
                    if msg['type'] == 'hand':
                        client['hand'] = msg['hand']
                    elif msg['type'] == 'start':
                        client['players'] = msg['players']
                    elif msg['type'] == 'log':
                        client['messages'].append(msg['content'])
                    elif msg['type'] == 'your_turn':
                        client['hand'] = msg.get('hand', client['hand'])
                        client['history'] = msg.get('history', client['history'])
                    elif msg['type'] == 'info':
                        client['messages'].append(msg['content'])
                    elif msg['type'] == 'end':
                        client['messages'].append(f"Gagnant : {msg['winner']}")
        except Exception as e:
            client['messages'].append(f"Erreur : {e}")
            break

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
