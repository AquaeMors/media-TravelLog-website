# Tiny Storage

A personal web app for organizing memories, media, and everyday life. The site is built around a clean, card-based dashboard and focused, purpose-driven sections.

---

## Overview

Tiny Storage groups features into clear spaces so they’re easy to find and expand over time:

- **Home Dashboard** – a card grid that previews each section.
- **Rosie & Tiny** – a shared space containing:
  - **Travel Log** – interactive map of trips with photo albums and notes.
  - **Dates** – plan ideas, mark them completed, and attach media.
- **Media Tracker** – track reading, shows, movies, anime/manga/manhwa, games, and more.
- **Fitness** – a place to record and review personal fitness activity and trends.

> Admins and approvers can edit card titles, descriptions, and cover images directly from the grid.

---

## Home Dashboard

- Responsive, card-based layout with large cover images.
- Each card is a deep link into its section and includes an **Edit** action (role-gated).
- “Stretched link” cards make the whole tile clickable while keeping buttons usable.
- Brand logo in the navbar returns to Home and includes hover/press feedback.

---

## Rosie & Tiny

A parent space with its own sub-menu. It currently includes **Travel Log** and **Dates**.

### Travel Log

- **Interactive Map**  
  View all locations on a Leaflet map. “Zoom to pins” fits the view to all trips. Clicking a pin opens the trip.

- **Trip Cards & Modals**  
  Each location has a card with an optional cover photo and media count. Opening a trip shows:
  - Key details (address, coordinates, created date).
  - Optional notes.
  - A responsive **gallery** with thumbnails and a “show more/less” toggle.

- **Comments & Reactions**  
  Per-trip comments with lightweight up/down reactions and time-ago stamps.
  
- **Creation & Editing**  
  Role-gated actions to add new locations, set coordinates, write notes, and upload photo batches. Thumbnails are generated for fast browsing.

### Dates

A structured space for planning and capturing date ideas.

- **Planned vs. Completed**  
  Two tabs organize ideas by status. Mark items completed with a single action.

- **Per-Date Details**  
  Each date has a modal with fields for title, template type, date/time, location, rating, cost, and notes.

- **Media Attachments**  
  Upload multiple **photos** (with thumbnails) and **short videos** for each date. Media displays in the same responsive gallery used by Travel Log.

- **Templates**  
  Dates are categorized (e.g., nature moments, trips, at-home nights, classes, builds/DIY, culture/events, service, media shares, milestones) so entries remain consistent while flexible.

---

## Media Tracker

A centralized tracker for personal media:

- Organize books, movies, shows, anime/manga/manhwa, games, and other media.
- Record progress, notes, tags, and ratings.
- Designed for quick lookup and lightweight updates.

*(The tracker is intentionally broad; it’s meant to be practical rather than prescriptive.)*

---

## Fitness

A space to log workouts and observe trends over time:

- Capture sessions and notes.
- Review activity at a glance and track personal goals.

---

## Accounts & Permissions

- **Sign-in required** for participation.
- **Approver role** for moderating user requests.
- **Edit permissions** gate actions like creating trips, uploading media, and editing cards.

---

## Design & UX

- Clean, dark-friendly visual style with rounded cards and soft shadows.
- Consistent layout patterns across sections (cards → modal detail → gallery).
- Media-first presentation with fast thumbnail rendering.
- Keyboard and pointer feedback on interactive elements.

---

## What’s Included, At a Glance

- Card dashboard with editable tiles and cover images  
- Shared **Rosie & Tiny** space with **Travel Log** and **Dates**
- Interactive map, trip modals, notes, and comment reactions
- Dates planner with status, details, and photo/video uploads
- Media Tracker for books, shows, films, anime/manga/manhwa, games
- Fitness logging space
- Role-based access with approver/admin capabilities
- Cohesive gallery and modal experience throughout the site
