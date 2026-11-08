# Trove

Trove is a personal long-content library: audio is the primary way to consume, text is the substrate for organization and retrieval.

## Content

**Item**:
One consumable content unit: a video, a podcast episode, or a book. In the MVP, one ingested URL produces at most one Item; playlist and multi-part URLs are rejected.
_Avoid_: Content, file, media

**Source**:
The origin of an Item: an original URL, platform, or local file path.
_Avoid_: Link, input

**Library**:
The user's complete collection of Items.
_Avoid_: Database, archive

**Content Package**:
The set of files that make up an Item in the Library: source metadata, audio, transcript, book file, and AI results. It is the unit of export.
_Avoid_: Folder, bundle

**Tag**:
A free-form, fine-grained classification generated at ingest and editable by the user.
_Avoid_: Topic (for the MVP), label, keyword

**Export**:
A portable zip of the Library (or a subset of Items) containing source metadata, audio, transcripts, book files, AI results, and a Markdown index.
_Avoid_: Backup, dump

## Processing and consumption

**Processing Run**:
One attempt to turn an Item's Source into consumable artifacts. A failed Run can be retried without repeating completed steps.
_Avoid_: Job, task

**Processing State**:
The state of a Processing Run: queued, downloading, extracting audio, transcribing, organizing, indexing, completed, or failed.
_Avoid_: Status (when referring to processing)

**Consumption State**:
The user's relationship to an Item: unstarted, in progress, or finished. It is independent of Processing State.
_Avoid_: Status (when referring to consumption), read/unread (for audio)

**Host**:
The machine or service that downloads, processes, stores, and serves the Library. The MVP Host is the user's Mac; cloud hosting is a later option, not an MVP requirement.
_Avoid_: Server, backend, desktop app

**Host Console**:
The Web UI and API served by the Host for adding, processing, managing, searching, and exporting the Library. It is not the primary consumption client.
_Avoid_: Admin panel, dashboard, consumer app

**Consumer Web Shell**:
A thin browser client for playback, transcript reading, Continue, and search-to-paragraph used to validate the MVP. It is expected to be replaced by the Android client.
_Avoid_: Web app, PWA (as the final product)
