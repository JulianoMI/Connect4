# Connect Four - Multiplayer Game

A real-time Connect Four game built with Python FastAPI, WebSockets, and modern web technologies. Play with friends or challenge the computer!

## Features

- 🎮 **Real-time multiplayer gameplay** using WebSockets
- 🔐 **Protected rooms** with optional password protection
- 👥 **2-player limit** per room (enforced automatically)
- 🤖 **Computer opponent** option for single-player games
- 🎨 **Modern, responsive UI** with beautiful animations
- 📱 **Mobile-friendly** design
- 💾 **SQLite database** for room and player management
- 🚀 **Ready for Vercel deployment**

## Game Rules

Connect Four is a two-player connection game in which the players first choose a color and then take turns dropping colored discs into a seven-column, six-row vertically suspended grid. The pieces fall straight down, occupying the lowest available space within the column. The objective is to be the first to form a horizontal, vertical, or diagonal line of four of one's own discs.

## Technology Stack

- **Backend**: Python FastAPI
- **WebSockets**: Real-time communication
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Deployment**: Vercel-ready

## Installation & Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd TwoPlayer
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python main.py
   ```

4. **Open your browser**
   Navigate to `http://localhost:8000`

### Vercel Deployment

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Deploy to Vercel**
   ```bash
   vercel
   ```

3. **Follow the prompts** to complete deployment

## How to Play

### Creating a Room
1. Enter a room name
2. Optionally set a password for protection
3. Click "Create Room"
4. Share the generated Room ID with friends

### Joining a Room
1. Enter the Room ID provided by your friend
2. Choose a unique username
3. Enter the password if the room is protected
4. Click "Join Room"

### Playing vs Computer
1. Enter any existing Room ID
2. Choose a username
3. Click "Play vs Computer"
4. The game will automatically add a computer opponent

### Gameplay
- Click on any column to drop your piece
- First player to connect 4 pieces wins
- Games automatically reset after completion
- Use "Reset Game" to start over anytime

## API Endpoints

- `GET /` - Main game interface
- `POST /create-room` - Create a new game room
- `POST /join-room` - Join an existing room
- `POST /join-vs-computer` - Join room with computer opponent
- `GET /room-info/{room_id}` - Get room information
- `WebSocket /ws/{room_id}/{player_id}` - Real-time game communication

## Database Schema

### Rooms Table
- `id`: Unique room identifier
- `name`: Room name
- `password`: Optional room password
- `max_players`: Maximum players allowed (default: 2)
- `current_players`: Current number of players
- `is_active`: Room status

### Players Table
- `id`: Unique player identifier
- `username`: Player display name
- `room_id`: Associated room
- `is_computer`: Whether player is AI opponent

### Games Table
- `id`: Unique game identifier
- `room_id`: Associated room
- `board_state`: Current game board state
- `current_player`: Active player
- `winner`: Winning player (if game over)
- `game_over`: Game completion status

## Security Features

- **Room Protection**: Optional password-protected rooms
- **Player Validation**: Username uniqueness per room
- **Player Limits**: Maximum 2 players per room enforced
- **Input Sanitization**: All user inputs are validated

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

If you encounter any issues or have questions, please open an issue on GitHub.

---

**Enjoy playing Connect Four! 🎉**
