from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import sqlite3
import uuid
import json
import os
from typing import Dict, List

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Check if running on Vercel
IS_VERCEL = os.getenv("VERCEL") == "1"

# Initialize database
def init_db():
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT,
            max_players INTEGER DEFAULT 2,
            current_players INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            room_id TEXT,
            is_computer BOOLEAN DEFAULT FALSE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            room_id TEXT,
            board_state TEXT,
            current_player TEXT,
            winner TEXT,
            game_over BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Clean up any orphaned players (optional - for debugging)
def cleanup_orphaned_players():
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # Delete players from rooms that don't exist
    cursor.execute('''
        DELETE FROM players 
        WHERE room_id NOT IN (SELECT id FROM rooms WHERE is_active = TRUE)
    ''')
    
    # Update room player counts to match actual player counts
    cursor.execute('''
        UPDATE rooms 
        SET current_players = (
            SELECT COUNT(*) 
            FROM players 
            WHERE players.room_id = rooms.id
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Cleaned up orphaned players and updated room counts")

# Run cleanup
cleanup_orphaned_players()

# WebSocket connection manager (only for localhost)
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast_to_room(self, message: str, room_id: str):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_text(message)
                except:
                    pass

manager = ConnectionManager()

# Game logic
class ConnectFourGame:
    def __init__(self):
        self.board = [[0 for _ in range(7)] for _ in range(6)]
        self.current_player = 1
        self.game_over = False
        self.winner = None
    
    def make_move(self, column: int) -> bool:
        if self.game_over or column < 0 or column >= 7:
            return False
        
        # Find the lowest empty row in the column
        for row in range(5, -1, -1):
            if self.board[row][column] == 0:
                self.board[row][column] = self.current_player
                
                if self.check_winner(row, column):
                    self.game_over = True
                    self.winner = self.current_player
                elif self.is_board_full():
                    self.game_over = True
                
                self.current_player = 3 - self.current_player  # Switch between 1 and 2
                return True
        return False
    
    def check_winner(self, row: int, col: int) -> bool:
        player = self.board[row][col]
        
        # Check horizontal
        for c in range(max(0, col-3), min(4, col+1)):
            if all(self.board[row][c+i] == player for i in range(4)):
                return True
        
        # Check vertical
        for r in range(max(0, row-3), min(3, row+1)):
            if all(self.board[r+i][col] == player for i in range(4)):
                return True
        
        # Check diagonal (top-left to bottom-right)
        for r in range(max(0, row-3), min(3, row+1)):
            for c in range(max(0, col-3), min(4, col+1)):
                if all(self.board[r+i][c+i] == player for i in range(4)):
                    return True
        
        # Check diagonal (top-right to bottom-left)
        for r in range(max(0, row-3), min(3, row+1)):
            for c in range(max(3, col), min(7, col+4)):
                if all(self.board[r+i][c-i] == player for i in range(4)):
                    return True
        
        return False
    
    def is_board_full(self) -> bool:
        return all(self.board[0][col] != 0 for col in range(7))
    
    def get_board_state(self):
        return self.board
    
    def reset(self):
        self.board = [[0 for _ in range(7)] for _ in range(6)]
        self.current_player = 1
        self.game_over = False
        self.winner = None

# Store games in memory
games: Dict[str, ConnectFourGame] = {}

@app.get("/")
async def read_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post("/create-room")
async def create_room(name: str = Form(...), password: str = Form(None), username: str = Form(...)):
    room_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO rooms (id, name, password, max_players, current_players)
        VALUES (?, ?, ?, ?, ?)
    ''', (room_id, name, password, 2, 1))
    
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    
    # Initialize game for this room
    games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"room_id": room_id, "name": name, "password": password, "player_id": player_id, "success": True}

@app.post("/join-room")
async def join_room(room_id: str = Form(...), username: str = Form(...), password: str = Form(None)):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # Check if room exists and password is correct
    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room[2] and room[2] != password:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    # Check if room is full
    current_players = room[5] if room[5] is not None else 0
    max_players = room[4] if room[4] is not None else 2
    if current_players >= max_players:
        conn.close()
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Check if username is already taken
    cursor.execute('SELECT * FROM players WHERE room_id = ? AND username = ?', (room_id, username))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Add player to room
    player_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    
    # Count actual players in the room and update
    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    actual_player_count = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE rooms SET current_players = ?
        WHERE id = ?
    ''', (actual_player_count, room_id))
    
    # Initialize game if not exists
    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"success": True, "player_id": player_id, "room_id": room_id}

@app.post("/add-computer-opponent")
async def add_computer_opponent(room_id: str = Form(...)):
    """Add a computer opponent to an existing room"""
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # Check if room exists
    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check current player count
    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    current_players = cursor.fetchone()[0]
    
    if current_players >= 2:
        conn.close()
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Add computer player
    computer_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, TRUE)
    ''', (computer_id, "Computer", room_id))
    
    # Update room player count
    cursor.execute('''
        UPDATE rooms SET current_players = 2
        WHERE id = ?
    ''', (room_id,))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Computer opponent added"}

@app.post("/join-vs-computer")
async def join_vs_computer(room_id: str = Form(...), username: str = Form(...), password: str = Form(None)):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # Check if room exists and password is correct
    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room[2] and room[2] != password:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    # Check if room is full
    current_players = room[5] if room[5] is not None else 0
    if current_players >= 2:
        conn.close()
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Check if username is already taken
    cursor.execute('SELECT * FROM players WHERE room_id = ? AND username = ?', (room_id, username))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Add human player
    player_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    
    # Add computer player
    computer_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, TRUE)
    ''', (computer_id, "Computer", room_id))
    
    # Count actual players in the room and update
    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    actual_player_count = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE rooms SET current_players = ?
        WHERE id = ?
    ''', (actual_player_count, room_id))
    
    # Initialize game
    games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"success": True, "player_id": player_id, "room_id": room_id}

@app.get("/room-info/{room_id}")
async def get_room_info(room_id: str):
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, COUNT(p.id) as player_count
        FROM rooms r
        LEFT JOIN players p ON r.id = p.room_id
        WHERE r.id = ?
        GROUP BY r.id
    ''', (room_id,))
    
    room = cursor.fetchone()
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    cursor.execute('SELECT username, is_computer FROM players WHERE room_id = ?', (room_id,))
    players = cursor.fetchall()
    
    conn.close()
    
    return {
        "id": room[0],
        "name": room[1],
        "max_players": room[3],
        "current_players": room[4],
        "players": [{"username": p[0], "is_computer": p[1]} for p in players]
    }

# Polling endpoints (for Vercel)
@app.get("/game-state/{room_id}")
async def get_game_state(room_id: str):
    """Get current game state for polling"""
    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    game = games[room_id]
    return {
        "board": game.get_board_state(),
        "current_player": game.current_player,
        "game_over": game.game_over,
        "winner": game.winner
    }

@app.post("/make-move")
async def make_move(room_id: str = Form(...), player_id: str = Form(...), column: int = Form(...)):
    """Make a move in the game (for polling mode)"""
    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    game = games[room_id]
    
    # Get player info to determine player number
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, is_computer FROM players WHERE id = ?', (player_id,))
    player_info = cursor.fetchone()
    
    if not player_info:
        conn.close()
        raise HTTPException(status_code=404, detail="Player not found")
    
    username, is_computer = player_info
    
    # Determine player number (1 for first human player, 2 for second human player)
    cursor.execute('''
        SELECT id FROM players 
        WHERE room_id = ? AND is_computer = FALSE 
        ORDER BY joined_at
    ''', (room_id,))
    human_players = cursor.fetchall()
    conn.close()
    
    player_number = None
    for i, (pid,) in enumerate(human_players):
        if pid == player_id:
            player_number = i + 1  # 1 for first player, 2 for second player
            break
    
    # Check if it's this player's turn
    if game.current_player != player_number:
        raise HTTPException(status_code=400, detail=f"It's not your turn! Current turn: {'Red Team' if game.current_player == 1 else 'Blue Team'}")
    
    # Check if the move is valid
    if column < 0 or column >= 7 or game.board[0][column] != 0:
        raise HTTPException(status_code=400, detail="Invalid move! Column is full or out of bounds.")
    
    # Make the move
    if game.make_move(column):
        # If playing against computer and it's computer's turn
        if not game.game_over and game.current_player == 2:
            # Check if there's a computer player in this room
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ? AND is_computer = TRUE', (room_id,))
            computer_count = cursor.fetchone()[0]
            conn.close()
            
            # Only make computer move if there's actually a computer player
            if computer_count > 0:
                import random
                valid_columns = [col for col in range(7) if game.board[0][col] == 0]
                if valid_columns:
                    computer_column = random.choice(valid_columns)
                    game.make_move(computer_column)
        
        return {
            "success": True,
            "board": game.get_board_state(),
            "current_player": game.current_player,
            "game_over": game.game_over,
            "winner": game.winner
        }
    
    raise HTTPException(status_code=400, detail="Invalid move")

@app.post("/reset-game")
async def reset_game(room_id: str = Form(...)):
    """Reset the game"""
    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    games[room_id].reset()
    
    return {
        "success": True,
        "board": games[room_id].get_board_state(),
        "current_player": games[room_id].current_player,
        "game_over": games[room_id].game_over,
        "winner": games[room_id].winner
    }

# WebSocket endpoint (only for localhost)
if not IS_VERCEL:
    @app.websocket("/ws/{room_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
        await manager.connect(websocket, room_id)
        
        try:
            # Get player info from database
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('SELECT username, is_computer FROM players WHERE id = ?', (player_id,))
            player_info = cursor.fetchone()
            conn.close()
            
            if not player_info:
                await websocket.close()
                return
            
            username, is_computer = player_info
            
            # Initialize game if not exists
            if room_id not in games:
                games[room_id] = ConnectFourGame()
            
            # Determine player number (1 for first human player, 2 for second human player)
            conn = sqlite3.connect('game.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM players 
                WHERE room_id = ? AND is_computer = FALSE 
                ORDER BY joined_at
            ''', (room_id,))
            human_players = cursor.fetchall()
            conn.close()
            
            player_number = None
            for i, (pid,) in enumerate(human_players):
                if pid == player_id:
                    player_number = i + 1  # 1 for first player, 2 for second player
                    break
            
            # Send current game state with player info
            game_state = {
                "type": "game_state",
                "board": games[room_id].get_board_state(),
                "current_player": games[room_id].current_player,
                "game_over": games[room_id].game_over,
                "winner": games[room_id].winner,
                "player_number": player_number,
                "username": username
            }
            await websocket.send_text(json.dumps(game_state))
            
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message["type"] == "make_move":
                    column = message["column"]
                    
                    # Check if it's this player's turn
                    if games[room_id].current_player != player_number:
                        # Send error message to this player only
                        error_message = {
                            "type": "error",
                            "message": f"It's not your turn! Current turn: {'Red Team' if games[room_id].current_player == 1 else 'Blue Team'}"
                        }
                        await websocket.send_text(json.dumps(error_message))
                        continue
                    
                    # Check if the move is valid
                    if column < 0 or column >= 7 or games[room_id].board[0][column] != 0:
                        error_message = {
                            "type": "error",
                            "message": "Invalid move! Column is full or out of bounds."
                        }
                        await websocket.send_text(json.dumps(error_message))
                        continue
                    
                    # Make the move
                    if games[room_id].make_move(column):
                        # Broadcast updated game state
                        game_state = {
                            "type": "game_state",
                            "board": games[room_id].get_board_state(),
                            "current_player": games[room_id].current_player,
                            "game_over": games[room_id].game_over,
                            "winner": games[room_id].winner
                        }
                        await manager.broadcast_to_room(json.dumps(game_state), room_id)
                        
                        # Only make computer moves if there's actually a computer player
                        if not games[room_id].game_over and games[room_id].current_player == 2:
                            # Check if there's a computer player in this room
                            conn = sqlite3.connect('game.db')
                            cursor = conn.cursor()
                            cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ? AND is_computer = TRUE', (room_id,))
                            computer_count = cursor.fetchone()[0]
                            conn.close()
                            
                            # Only make computer move if there's actually a computer player
                            if computer_count > 0:
                                # Simple AI: make a random valid move
                                import random
                                valid_columns = [col for col in range(7) if games[room_id].board[0][col] == 0]
                                if valid_columns:
                                    computer_column = random.choice(valid_columns)
                                    games[room_id].make_move(computer_column)
                                    
                                    # Broadcast computer's move
                                    game_state = {
                                        "type": "game_state",
                                        "board": games[room_id].get_board_state(),
                                        "current_player": games[room_id].current_player,
                                        "game_over": games[room_id].game_over,
                                        "winner": games[room_id].winner
                                    }
                                    await manager.broadcast_to_room(json.dumps(game_state), room_id)
                
                elif message["type"] == "reset_game":
                    games[room_id].reset()
                    game_state = {
                        "type": "game_state",
                        "board": games[room_id].get_board_state(),
                        "current_player": games[room_id].current_player,
                        "game_over": games[room_id].game_over,
                        "winner": games[room_id].winner
                    }
                    await manager.broadcast_to_room(json.dumps(game_state), room_id)
        
        except WebSocketDisconnect:
            manager.disconnect(websocket, room_id)

@app.get("/reset-db")
async def reset_database():
    """Reset database for testing"""
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM players')
    cursor.execute('DELETE FROM rooms')
    cursor.execute('DELETE FROM games')
    
    conn.commit()
    conn.close()
    
    # Clear in-memory games
    games.clear()
    
    return {"success": True, "message": "Database reset"}

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    print(f"Starting Connect Four game server on {host}:{port}")
    print(f"Running in {'Vercel' if IS_VERCEL else 'Localhost'} mode")
    uvicorn.run(app, host=host, port=port)
