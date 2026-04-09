# Design System Specification: The Silicon Intelligence Framework

## 1. Overview & Creative North Star
**Creative North Star: The Digital Architect**
This design system moves away from the "chat bubble" tropes of consumer AI. Instead, it adopts the persona of a high-end technical consultant—an expert in the intricate world of semiconductor logistics. The experience is cinematic, characterized by deep-space backgrounds and illuminated technical data.

**Design Philosophy: Cinematic Precision**
To break the "template" look, we utilize a **non-linear layout strategy**. We favor intentional asymmetry—where data visualizations might bleed off the edge of a container, or typography is scaled to "Display" sizes to act as a structural element rather than just a label. We replace rigid grids with "gravitational" layouts, where elements feel held in place by logic and light rather than boxes and lines.

---

## 2. Colors & Surface Logic

### The Palette
The color strategy is "Luminescent Dark Mode." We use a deep, obsidian-green base to provide the "intelligence" backdrop, allowing our high-frequency accents to "pop" like illuminated circuitry.

*   **Background (#03170F):** The deep green-black void. Never use pure black (#000).
*   **Primary Accent (#5AEB56):** "Neon Pulse." Reserved for active AI processing and primary CTAs.
*   **Secondary (#098F3B):** "Forest Logic." Used for stable states and secondary brand elements.
*   **Data Highlight (#3CF2FF):** "Soft Cyan." Specifically for technical specs, silicon wafer data, and fluctuating metrics.

### The "No-Line" Rule
**Explicit Instruction:** 1px solid borders are strictly prohibited for sectioning. We do not "box in" information. Boundaries must be defined through:
1.  **Tonal Shifts:** Placing a `surface-container-high` card against a `surface` background.
2.  **Luminescent Shadows:** Using a soft green glow to imply the edge of a container.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical, semi-transparent layers.
*   **Base Layer:** `surface` (#03170F)
*   **Nesting Level 1:** `surface-container-low` (#0A1F17) for large layout sections.
*   **Nesting Level 2:** `surface-container-highest` (#243930) for interactive modules or AI response blocks.

### The Glass & Gradient Rule
Floating elements (modals, tooltips, hover-cards) must use **Glassmorphism**. 
*   **Style:** `surface-variant` at 60% opacity with a `20px` backdrop-blur. 
*   **Signature Texture:** Use a linear gradient from `primary` (#AEFFA0) to `primary-container` (#5AEB56) at a 45-degree angle for high-value action buttons. This provides a "liquid light" feel.

---

## 3. Typography: High-Contrast Authority

We use a dual-font strategy to balance futuristic tech with editorial precision.

*   **Display & Headlines (Space Grotesk):** A geometric sans-serif that feels engineered. Use `display-lg` (3.5rem) with tightened letter-spacing (-0.02em) for impactful data points (e.g., "98% Yield").
*   **Body & Titles (Manrope):** A modern, highly legible sans-serif. Manrope provides the "trust" factor.
*   **Technical Labels (Inter):** Used for micro-data and tabular content where clarity is non-negotiable.

**Hierarchy as Identity:** 
Always pair a `label-md` (All Caps, tracked out 10%) above a `headline-sm` to create an editorial "Intro" look. This signals that the AI is presenting curated, expert information.

---

## 4. Elevation & Depth

### The Layering Principle
Forget traditional drop shadows. We use **Tonal Layering**. To elevate an element, move it up the surface tier:
*   Place a `surface-container-lowest` card on a `surface-container-low` section. This creates a "recessed" look, perfect for input fields.
*   Place a `surface-bright` element on a `surface` background to create "lift."

### Ambient Shadows
For floating AI elements, use a "Green Ambient Glow":
*   **Color:** `primary` (#5AEB56) at 8% opacity.
*   **Blur:** 40px to 60px. 
*   This mimics the light cast by a high-end monitor in a dark room.

### The "Ghost Border" Fallback
If a separation is required for accessibility, use the `outline-variant` token (#3D4A39) at **15% opacity**. It should be felt, not seen.

---

## 5. Components & UI Patterns

### Buttons: The Kinetic Trigger
*   **Primary:** Gradient fill (`primary` to `primary-container`). Roundedness: `sm` (0.125rem). This sharp corner feels more "industrial" and "premium" than round pills.
*   **Secondary:** Ghost style. No background. `outline-variant` at 20% opacity. 100% white text.
*   **States:** On hover, the primary button should gain a `primary_fixed` outer glow (8px blur).

### Cards & AI Responses
*   **Rule:** Forbid divider lines. Use `spacing-6` (2rem) of vertical whitespace to separate header, body, and footer.
*   **Styling:** Use `surface-container-high` with a subtle top-to-bottom gradient.

### Futuristic Wireframe Viz (Custom Component)
*   When the AI is "Thinking," display a low-opacity wireframe grid using `tertiary` (#3CF2FF) at 10% opacity. This reinforces the "active processing" atmosphere.

### Input Fields: The Command Line
*   Minimalist design. A single underline of `outline` (#879580) that transforms into a `primary` neon glow when active. 
*   **Typography:** Use `title-md` for user input to give the user's commands a sense of importance.

---

## 6. Do’s and Don’ts

### Do:
*   **Do** use asymmetrical margins. For example, give a data visualization 4rem of padding on the left and 8rem on the right to create "cinematic tension."
*   **Do** use the `soft cyan` (#3CF2FF) exclusively for "new" or "volatile" data points.
*   **Do** use `backdrop-blur` on the navigation bar to allow content to bleed through as the user scrolls.

### Don't:
*   **Don't** use standard "Success" green. Always use the system's `primary` (#5AEB56) or `secondary` (#098F3B).
*   **Don't** use 100% opaque borders. They break the glassmorphic illusion.
*   **Don't** use "Information Blue." Use `tertiary-fixed` (#78F5FF) for all informational callouts.
*   **Don't** over-round corners. Stick to `sm` (0.125rem) or `md` (0.375rem) to maintain a professional, enterprise-grade edge.