from fastapi import FastAPI, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uuid
import json
import os
from typing import Dict, List
from datetime import datetime

app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")


IS_VERCEL = os.getenv("VERCEL") == "1"


if not IS_VERCEL:
    from fastapi import WebSocket, WebSocketDisconnect
    import sqlite3


vercel_rooms = {}
vercel_players = {}
vercel_games = {}


def get_db_connection():
    """Get database connection - file for localhost only"""
    if IS_VERCEL:
        raise Exception("Database not available on Vercel - using in-memory storage")
    else:

        return sqlite3.connect('game.db')


def init_db():
    if IS_VERCEL:
        print("Running on Vercel - skipping database initialization")
        return
    
    conn = get_db_connection()
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
            current_player INTEGER DEFAULT 1,
            game_over BOOLEAN DEFAULT FALSE,
            winner INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    ''')
    
    conn.commit()
    conn.close()


try:
    init_db()
    print("Database initialized successfully")
except Exception as e:
    print(f"Error initializing database: {e}")


def cleanup_orphaned_players():
    if IS_VERCEL:
        print("Running on Vercel - skipping cleanup")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    
    cursor.execute('''
        DELETE FROM players 
        WHERE room_id NOT IN (SELECT id FROM rooms WHERE is_active = TRUE)
    ''')
    
    
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


try:
    cleanup_orphaned_players()
except Exception as e:
    print(f"Error during cleanup: {e}")


if not IS_VERCEL:
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


class ConnectFourGame:
    def __init__(self):
        self.board = [[0 for _ in range(7)] for _ in range(6)]
        self.current_player = 1
        self.game_over = False
        self.winner = None
    
    def make_move(self, column):
        if self.game_over:
            return False
        
        
        for row in range(5, -1, -1):
            if self.board[row][column] == 0:
                self.board[row][column] = self.current_player
                
                
                if self.check_win(row, column):
                    self.game_over = True
                    self.winner = self.current_player
                elif self.is_board_full():
                    self.game_over = True
                else:
                    self.current_player = 3 - self.current_player  
                
                return True
        return False
    
    def check_win(self, row, col):
        player = self.board[row][col]
        
        
        for c in range(max(0, col-3), min(4, col+1)):
            if all(self.board[row][c+i] == player for i in range(4)):
                return True
        
        
        for r in range(max(0, row-3), min(3, row+1)):
            if all(self.board[r+i][col] == player for i in range(4)):
                return True
        
        
        for r in range(max(0, row-3), min(3, row+1)):
            for c in range(max(0, col-3), min(4, col+1)):
                if all(self.board[r+i][c+i] == player for i in range(4)):
                    return True
        
        
        for r in range(max(0, row-3), min(3, row+1)):
            for c in range(max(3, col), min(7, col+4)):
                if all(self.board[r+i][c-i] == player for i in range(4)):
                    return True
        
        return False
    
    def is_board_full(self):
        return all(self.board[0][col] != 0 for col in range(7))
    
    def get_board_state(self):
        return self.board
    
    def reset(self):
        self.board = [[0 for _ in range(7)] for _ in range(6)]
        self.current_player = 1
        self.game_over = False
        self.winner = None


games: Dict[str, ConnectFourGame] = {}

@app.get("/")
async def read_root():
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        print(f"Error serving index.html: {e}")
        return HTMLResponse(content="<h1>Connect Four Game - Error loading page</h1><p>Please try refreshing the page.</p>", status_code=500)


def create_room_vercel(name: str, password: str, username: str):
    """Create room using in-memory storage for Vercel"""
    room_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    
    vercel_rooms[room_id] = {
        "id": room_id,
        "name": name,
        "password": password,
        "max_players": 2,
        "current_players": 1,
        "is_active": True,
        "created_at": datetime.now().isoformat()
    }
    
    vercel_players[player_id] = {
        "id": player_id,
        "username": username,
        "room_id": room_id,
        "is_computer": False,
        "joined_at": datetime.now().isoformat()
    }
    

    games[room_id] = ConnectFourGame()
    
    return {"room_id": room_id, "name": name, "password": password, "player_id": player_id, "success": True}

def join_room_vercel(room_id: str, username: str, password: str):
    """Join room using in-memory storage for Vercel"""
    if room_id not in vercel_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = vercel_rooms[room_id]
    if not room["is_active"]:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room["password"] and room["password"] != password:
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    if room["current_players"] >= room["max_players"]:
        raise HTTPException(status_code=400, detail="Room is full")
    

    for player in vercel_players.values():
        if player["room_id"] == room_id and player["username"] == username:
            raise HTTPException(status_code=400, detail="Username already taken")
    

    player_id = str(uuid.uuid4())
    vercel_players[player_id] = {
        "id": player_id,
        "username": username,
        "room_id": room_id,
        "is_computer": False,
        "joined_at": datetime.now().isoformat()
    }
    

    player_count = sum(1 for p in vercel_players.values() if p["room_id"] == room_id)
    vercel_rooms[room_id]["current_players"] = player_count
    

    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    return {"success": True, "player_id": player_id, "room_id": room_id}

def get_room_info_vercel(room_id: str):
    """Get room info using in-memory storage for Vercel"""
    if room_id not in vercel_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = vercel_rooms[room_id]
    players = [p for p in vercel_players.values() if p["room_id"] == room_id]
    
    return {
        "id": room["id"],
        "name": room["name"],
        "max_players": room["max_players"],
        "current_players": room["current_players"],
        "players": [{"username": p["username"], "is_computer": p["is_computer"]} for p in players]
    }

def make_move_vercel(room_id: str, player_id: str, column: int):
    """Make move using in-memory storage for Vercel"""
    if room_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if player_id not in vercel_players:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player = vercel_players[player_id]
    if player["room_id"] != room_id:
        raise HTTPException(status_code=400, detail="Player not in this room")
    

    human_players = [p for p in vercel_players.values() if p["room_id"] == room_id and not p["is_computer"]]
    human_players.sort(key=lambda x: x["joined_at"])
    
    player_number = None
    for i, p in enumerate(human_players):
        if p["id"] == player_id:
            player_number = i + 1
            break
    
    if player_number is None:
        raise HTTPException(status_code=400, detail="Player not found")
    

    if games[room_id].current_player != player_number:
        raise HTTPException(status_code=400, detail=f"It's not your turn! Current turn: {'Red Team' if games[room_id].current_player == 1 else 'Blue Team'}")
    

    if column < 0 or column >= 7 or games[room_id].board[0][column] != 0:
        raise HTTPException(status_code=400, detail="Invalid move! Column is full or out of bounds.")

    if games[room_id].make_move(column):
        return {"success": True}
    else:
        raise HTTPException(status_code=400, detail="Invalid move")

def reset_game_vercel(room_id: str):
    """Reset game using in-memory storage for Vercel"""
    if room_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    games[room_id].reset()
    return {"success": True}

def add_computer_opponent_vercel(room_id: str):
    """Add computer opponent using in-memory storage for Vercel"""
    if room_id not in vercel_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    

    for player in vercel_players.values():
        if player["room_id"] == room_id and player["is_computer"]:
            raise HTTPException(status_code=400, detail="Computer opponent already exists")
    

    computer_id = str(uuid.uuid4())
    vercel_players[computer_id] = {
        "id": computer_id,
        "username": "Computer",
        "room_id": room_id,
        "is_computer": True,
        "joined_at": datetime.now().isoformat()
    }
    

    player_count = sum(1 for p in vercel_players.values() if p["room_id"] == room_id)
    vercel_rooms[room_id]["current_players"] = player_count
    
    return {"success": True}


@app.post("/create-room")
async def create_room(name: str = Form(...), password: str = Form(None), username: str = Form(...)):
    if IS_VERCEL:
        return create_room_vercel(name, password or "", username)
    

    room_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO rooms (id, name, password, max_players, current_players)
        VALUES (?, ?, ?, ?, ?)
    ''', (room_id, name, password, 2, 1))
    
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    

    games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"room_id": room_id, "name": name, "password": password, "player_id": player_id, "success": True}

@app.post("/join-room")
async def join_room(room_id: str = Form(...), username: str = Form(...), password: str = Form(None)):
    if IS_VERCEL:
        return join_room_vercel(room_id, username, password or "")
    

    conn = get_db_connection()
    cursor = conn.cursor()
    

    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room[2] and room[2] != password:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect password")
    

    current_players = room[5] if room[5] is not None else 0
    max_players = room[4] if room[4] is not None else 2
    if current_players >= max_players:
        conn.close()
        raise HTTPException(status_code=400, detail="Room is full")
    

    cursor.execute('SELECT * FROM players WHERE room_id = ? AND username = ?', (room_id, username))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    

    player_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    

    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    actual_player_count = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE rooms SET current_players = ?
        WHERE id = ?
    ''', (actual_player_count, room_id))
    

    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"success": True, "player_id": player_id, "room_id": room_id}

@app.post("/join-vs-computer")
async def join_vs_computer(room_id: str = Form(...), username: str = Form(...), password: str = Form(None)):
    if IS_VERCEL:

        result = join_room_vercel(room_id, username, password or "")
        add_computer_opponent_vercel(room_id)
        return result
    

    conn = get_db_connection()
    cursor = conn.cursor()
    

    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room[2] and room[2] != password:
        conn.close()
        raise HTTPException(status_code=401, detail="Incorrect password")
    

    current_players = room[5] if room[5] is not None else 0
    max_players = room[4] if room[4] is not None else 2
    if current_players >= max_players:
        conn.close()
        raise HTTPException(status_code=400, detail="Room is full")
    

    cursor.execute('SELECT * FROM players WHERE room_id = ? AND username = ?', (room_id, username))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    

    player_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, FALSE)
    ''', (player_id, username, room_id))
    

    computer_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, TRUE)
    ''', (computer_id, "Computer", room_id))
    

    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    actual_player_count = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE rooms SET current_players = ?
        WHERE id = ?
    ''', (actual_player_count, room_id))
    

    if room_id not in games:
        games[room_id] = ConnectFourGame()
    
    conn.commit()
    conn.close()
    
    return {"success": True, "player_id": player_id, "room_id": room_id}

@app.get("/room-info/{room_id}")
async def get_room_info(room_id: str):
    if IS_VERCEL:
        return get_room_info_vercel(room_id)
    

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
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
        "max_players": room[4],
        "current_players": room[5],
        "players": [{"username": p[0], "is_computer": p[1]} for p in players]
    }

@app.get("/game-state/{room_id}")
async def get_game_state(room_id: str):
    if room_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return {
        "board": games[room_id].get_board_state(),
        "current_player": games[room_id].current_player,
        "game_over": games[room_id].game_over,
        "winner": games[room_id].winner
    }

@app.post("/make-move")
async def make_move(room_id: str = Form(...), player_id: str = Form(...), column: int = Form(...)):
    if IS_VERCEL:
        return make_move_vercel(room_id, player_id, column)
    

    if room_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username, is_computer FROM players WHERE id = ?', (player_id,))
    player_info = cursor.fetchone()
    conn.close()
    
    if not player_info:
        raise HTTPException(status_code=404, detail="Player not found")
    
    username, is_computer = player_info
    

    conn = get_db_connection()
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
            player_number = i + 1
            break
    
    if player_number is None:
        raise HTTPException(status_code=400, detail="Player not found")
    

    if games[room_id].current_player != player_number:
        raise HTTPException(status_code=400, detail=f"It's not your turn! Current turn: {'Red Team' if games[room_id].current_player == 1 else 'Blue Team'}")
    

    if column < 0 or column >= 7 or games[room_id].board[0][column] != 0:
        raise HTTPException(status_code=400, detail="Invalid move! Column is full or out of bounds.")
    
    # Make the move
    if games[room_id].make_move(column):
        return {"success": True}
    else:
        raise HTTPException(status_code=400, detail="Invalid move")

@app.post("/reset-game")
async def reset_game(room_id: str = Form(...)):
    if IS_VERCEL:
        return reset_game_vercel(room_id)
    

    if room_id not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    games[room_id].reset()
    return {"success": True}

@app.post("/add-computer-opponent")
async def add_computer_opponent(room_id: str = Form(...)):
    if IS_VERCEL:
        return add_computer_opponent_vercel(room_id)
    

    conn = get_db_connection()
    cursor = conn.cursor()
    

    cursor.execute('SELECT * FROM rooms WHERE id = ? AND is_active = TRUE', (room_id,))
    room = cursor.fetchone()
    
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Room not found")
    

    cursor.execute('SELECT * FROM players WHERE room_id = ? AND is_computer = TRUE', (room_id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Computer opponent already exists")
    

    computer_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO players (id, username, room_id, is_computer)
        VALUES (?, ?, ?, TRUE)
    ''', (computer_id, "Computer", room_id))
    

    cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ?', (room_id,))
    actual_player_count = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE rooms SET current_players = ?
        WHERE id = ?
    ''', (actual_player_count, room_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True}

@app.post("/reset-db")
async def reset_database():
    """Reset database for testing purposes"""
    if IS_VERCEL:

        vercel_rooms.clear()
        vercel_players.clear()
        games.clear()
        return {"success": True, "message": "Vercel in-memory storage cleared"}
    

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM games')
    cursor.execute('DELETE FROM players')
    cursor.execute('DELETE FROM rooms')
    
    conn.commit()
    conn.close()
    

    games.clear()
    
    return {"success": True, "message": "Database reset successfully"}


if not IS_VERCEL:
    @app.websocket("/ws/{room_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
        await manager.connect(websocket, room_id)
        
        try:

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT username, is_computer FROM players WHERE id = ?', (player_id,))
            player_info = cursor.fetchone()
            conn.close()
            
            if not player_info:
                await websocket.close()
                return
            
            username, is_computer = player_info
            

            if room_id not in games:
                games[room_id] = ConnectFourGame()
            
            
            conn = get_db_connection()
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
                    player_number = i + 1  
                    break
            
            
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
                    
                    
                    if games[room_id].current_player != player_number:
                        
                        error_message = {
                            "type": "error",
                            "message": f"It's not your turn! Current turn: {'Red Team' if games[room_id].current_player == 1 else 'Blue Team'}"
                        }
                        await websocket.send_text(json.dumps(error_message))
                        continue
                    
                    
                    if column < 0 or column >= 7 or games[room_id].board[0][column] != 0:
                        error_message = {
                            "type": "error",
                            "message": "Invalid move! Column is full or out of bounds."
                        }
                        await websocket.send_text(json.dumps(error_message))
                        continue
                    
                   
                    if games[room_id].make_move(column):
                        
                        game_state = {
                            "type": "game_state",
                            "board": games[room_id].get_board_state(),
                            "current_player": games[room_id].current_player,
                            "game_over": games[room_id].game_over,
                            "winner": games[room_id].winner
                        }
                        await manager.broadcast_to_room(json.dumps(game_state), room_id)
                        
                       
                        if not games[room_id].game_over and games[room_id].current_player == 2:
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            cursor.execute('SELECT COUNT(*) FROM players WHERE room_id = ? AND is_computer = TRUE', (room_id,))
                            computer_count = cursor.fetchone()[0]
                            conn.close()
                            
                            if computer_count > 0:
                                
                                import random
                                valid_moves = [col for col in range(7) if games[room_id].board[0][col] == 0]
                                if valid_moves:
                                    ai_column = random.choice(valid_moves)
                                    games[room_id].make_move(ai_column)
                                    
                                    
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

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
