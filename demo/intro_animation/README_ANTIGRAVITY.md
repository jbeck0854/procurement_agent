# Instructions for Antigravity UI Agent

This folder (`demo/intro_animation`) serves as the sandbox for regenerating the "Pegasus-style" Chatbot Intro Animation.

## Environment Context
- This environment **does not** have Node.js / npm installed. 
- You must build the animation as **pure HTML/CSS/JavaScript (Canvas/WebGL)** directly into `index.html` and `style.css`. No React, no Vite.
- Use CDN links for any libraries you need (e.g., `three.js`, `gsap`, `framer-motion` via ESM, etc.).

## Your Blueprint
1. The user's exact specification for the 5-stage deep-space fiber optic animation (Green Series) dictates the visual narrative.
2. Edit `index.html` to inject your structure where marked `<!-- [ANTIGRAVITY AGENT]: Inject ... -->`.
3. You can completely replace `style.css` with your design logic, but please keep the `#launch-chatbot-btn` properties as they align perfectly with the target Streamlit application.
4. **CRITICAL**: The button `LAUNCH CHATBOT` must be hidden initially. When your animation hits the final stage (the dashboard finishes loading), execute JS to reveal it:
   ```javascript
   document.getElementById('launch-chatbot-btn').classList.remove('hidden-btn');
   document.getElementById('launch-chatbot-btn').classList.add('visible-btn');
   ```

Do not modify any Streamlit Python files outside of this `intro_animation` folder.
