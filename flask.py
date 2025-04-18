from bottle import Bottle, run, request, redirect, template, response
import socket
import threading
import json

app = Bottle()

# Configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 12345
ADMIN_PASSWORD = 'loveletter'

# Global state
sock = None
buffer = ""
messages = []
hand = []
players = []
history = []
authenticated = False

LOGIN_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Connexion Love Letter</title></head>
<body>
<h2>Connexion</h2>
<form method="post">
    Mot de passe : <input type="password" name="password">
    <input type="submit" value="Entrer">
</form>
</body>
</html>
'''

GAME_HTML = '''
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
<h2>Bienvenue dans Love Letter</h2>
<p><strong>Joueurs :</strong> {{players}}</p>
<p><strong>Ta main :</strong> {{hand}}</p>
<form method="post" action="/play">
    <p>
        Choisis une carte :
        <select name="card">
            % for c in hand:
            <option value="{{c}}">{{c}}</option>
            % end
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
% for joueur, cartes in player_history.items():
    <strong>{{joueur}}</strong>: {{', '.join(cartes) if cartes else '---'}}<br>
% end
</div>

<h3>Messages</h3>
<ul>
% for m in messages:
    <li>{{m}}</li>
% end
</ul>

<form method="post" action="/ready">
    <button type="submit">Je suis prêt !</button>
</form>
</body>
</html>
'''

@app.route('/', method=['GET', 'POST'])
def login():
    global authenticated
    if request.method == 'POST':
        if request.forms.get('password') == ADMIN_PASSWORD:
            authenticated = True
            redirect('/game')
    return LOGIN_HTML

@app.route('/game')
def game():
    if not authenticated:
        redirect('/')
    player_history = {}
    for entry in history:
        joueur = entry['player']
        carte = entry['card']
        player_history.setdefault(joueur, []).append(carte)
    return template(GAME_HTML, hand=hand, players=players, messages=messages[-10:], history=history, player_history=player_history)

@app.route('/play', method='POST')
def play():
    if not authenticated:
        redirect('/')
    card = request.forms.get('card')
    target = request.forms.get('target')
    guess = request.forms.get('guess')
    msg = {
        'type': 'play',
        'card': card,
        'target': players.index(target) if target in players else None,
        'guess': guess or None
    }
    if sock:
        sock.send((json.dumps(msg) + '\n').encode())
    redirect('/game')

@app.route('/ready', method='POST')
def ready():
    if not authenticated:
        redirect('/')
    if sock:
        sock.send((json.dumps({"type": "ready"}) + '\n').encode())
    redirect('/game')

# Socket communication
def receive_from_server():
    global buffer, hand, players, messages, history
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
                        hand = msg['hand']
                    elif msg['type'] == 'start':
                        players = msg['players']
                    elif msg['type'] == 'log':
                        messages.append(msg['content'])
                    elif msg['type'] == 'your_turn' and 'hand' in msg:
                        hand = msg['hand']
                        history = msg.get('history', history)
                    elif msg['type'] == 'info':
                        messages.append(msg['content'])
                    elif msg['type'] == 'end':
                        messages.append(f"Gagnant : {msg['winner']}")
        except Exception as e:
            messages.append(f"Erreur de réception : {e}")
            break

# Initialisation
if __name__ == '__main__':
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_HOST, SERVER_PORT))
    name = input("Entrez votre nom : ")
    sock.send((json.dumps({"type": "name", "name": name}) + '\n').encode())
    threading.Thread(target=receive_from_server, daemon=True).start()
    run(app, host='0.0.0.0', port=5000)
