import os
from pathlib import Path

def setup_frontend():
    os.makedirs("frontend/src/components", exist_ok=True)
    os.makedirs("frontend/public", exist_ok=True)
    
    with open("frontend/package.json", "w") as f:
        f.write('''{
  "name": "quantai-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.6.0",
    "lucide-react": "^0.292.0",
    "plotly.js-dist-min": "^2.27.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-plotly.js": "^2.6.0",
    "react-markdown": "^9.0.1",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.37",
    "@types/react-dom": "^18.2.15",
    "@types/react-plotly.js": "^2.6.3",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.31",
    "tailwindcss": "^3.3.5",
    "typescript": "^5.2.2",
    "vite": "^5.0.0"
  }
}''')

    with open("frontend/vite.config.ts", "w") as f:
        f.write('''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})''')

    with open("frontend/tsconfig.json", "w") as f:
        f.write('''{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}''')

    with open("frontend/tsconfig.node.json", "w") as f:
        f.write('''{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}''')

    with open("frontend/tailwind.config.js", "w") as f:
        f.write('''/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}''')

    with open("frontend/postcss.config.js", "w") as f:
        f.write('''export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}''')

    with open("frontend/index.html", "w") as f:
        f.write('''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>QuantAI AI</title>
  </head>
  <body class="bg-slate-50 text-slate-900 font-sans">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>''')

    with open("frontend/src/index.css", "w") as f:
        f.write('''@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-slate-50 text-slate-900;
  }
}
''')

    with open("frontend/src/main.tsx", "w") as f:
        f.write('''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)''')

    with open("frontend/src/App.tsx", "w") as f:
        f.write('''import React, { useState } from 'react';

function App() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<any[]>([]);

  const handleQuery = async () => {
    if (!query) return;
    
    const newMsg = { role: 'user', content: query };
    setMessages(prev => [...prev, newMsg]);
    setQuery('');
    
    // Quick mock for now. In real app, we'd use SSE.
    try {
      const res = await fetch('http://localhost:8000/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query })
      });
      // Stream reading logic goes here
    } catch(err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen p-8 flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold mb-8 text-indigo-600">QuantAI AI</h1>
      
      <div className="w-full max-w-3xl bg-white p-6 rounded-xl shadow-sm border border-slate-200 mb-6 min-h-[400px]">
         {messages.map((m, i) => (
           <div key={i} className={`mb-4 p-4 rounded-lg ${m.role === 'user' ? 'bg-indigo-50 text-indigo-900 ml-auto w-3/4' : 'bg-slate-50 border border-slate-100 w-full'}`}>
             {m.content}
           </div>
         ))}
      </div>

      <div className="w-full max-w-3xl flex gap-2">
        <input 
          type="text" 
          className="flex-1 p-4 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          placeholder="Ask a question about your data..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
        />
        <button 
          onClick={handleQuery}
          className="px-8 py-4 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-medium"
        >
          Ask
        </button>
      </div>
    </div>
  );
}

export default App;
''')

if __name__ == '__main__':
    setup_frontend()
