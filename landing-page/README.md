# VoiceKhata Landing Page

This is a judge-friendly landing page for the VoiceKhata project (voice-first udhaar tracking). It’s a static HTML/CSS/JS page with a built-in demo simulator so you can show the flow even if WhatsApp isn’t available during judging.

## Project Structure

```
landing-page
├── src
│   ├── index.html        # Main HTML document for the landing page
│   ├── styles
│   │   └── main.css      # CSS styles for the landing page
│   ├── scripts
│   │   └── main.js       # JavaScript code for interactivity
│   └── types
│       └── index.ts      # TypeScript types and interfaces
├── package.json          # npm configuration file
├── tsconfig.json         # TypeScript configuration file
└── README.md             # Project documentation
```

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/pathan-07/Hacksprint-SSIU.git
   cd Hacksprint-SSIU/landing-page
   ```

2. **Install dependencies:**
   Make sure you have Node.js installed. Then run:
   ```bash
   npm install
   ```

3. **Run the project (recommended):**
   ```bash
   npm start
   ```
   This runs `live-server` on the `src/` folder.

4. **Optional: check backend health from the page:**
   - Start your FastAPI server (default: `http://localhost:8000`)
   - On the landing page, click **Check API** to call `/health`

## Features

- Modern, responsive UI (hero + problem/solution + demo + stack + FAQ)
- Live demo (calls backend `/demo/text`, `/demo/confirm`, `/demo/entries`)
- Offline fallback simulator (if backend/CORS is unavailable)
- Backend health checker (calls `/health` on your FastAPI server)

## Usage Guidelines

- Edit `src/index.html` for copy/sections.
- Edit `src/styles/main.css` for styling.
- Edit `src/scripts/main.js` for interactivity.

## Contributing

Feel free to submit issues or pull requests if you have suggestions or improvements for the project.