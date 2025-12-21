"""MCP Prompts - Guide AI behavior for common Anki tasks.

Prompts provide structured instructions for the AI to follow when performing
specific tasks. They don't access Anki data directly - they just generate
helpful guidance text.
"""


def register_all_prompts(mcp) -> None:
    """Register all MCP prompts with the server."""

    # ========================================================================
    # REVIEW SESSION
    # ========================================================================

    @mcp.prompt(
        name="review_session",
        description="Guide for conducting an Anki review session with a user"
    )
    def review_session(
        deck_name: str = "Default",
        card_limit: int = 20,
        review_style: str = "interactive"
    ) -> str:
        if review_style == "quick":
            style_instructions = """
QUICK REVIEW MODE:
- Present cards rapidly with minimal discussion
- Show question, wait for user signal, show answer
- Rate based on user's quick self-assessment (Again/Hard/Good/Easy)
- Aim for efficient coverage without deep exploration"""
        else:
            style_instructions = """
INTERACTIVE REVIEW MODE:
- Present each card's question and wait for the user's answer
- After they respond, reveal the answer and discuss if needed
- Help them understand concepts they struggle with
- Provide mnemonics or explanations when helpful
- Rate cards based on quality of their recall:
  * Again (1): Completely forgot or major errors
  * Hard (2): Struggled but got it eventually
  * Good (3): Correct with reasonable effort
  * Easy (4): Instant, effortless recall"""

        return f"""You are helping the user conduct an Anki review session.

SESSION PARAMETERS:
- Deck: "{deck_name}"
- Cards to review: up to {card_limit}
- Style: {review_style}
{style_instructions}

WORKFLOW:
1. First, sync to get latest data: Use the sync tool
2. Get due cards: Use get_due_cards with deck="{deck_name}" and limit={card_limit}
3. For each card, use present_card to get card content
4. Present the question to the user
5. Wait for their response
6. Show the answer and evaluate their response
7. Use rate_card to record their performance
8. Move to the next card

IMPORTANT GUIDELINES:
- Always sync before starting to ensure up-to-date card data
- Never skip cards - review them in the order provided
- Be encouraging but honest about mistakes
- If the user wants to stop early, that's fine - sync before ending
- Track progress: "Card X of Y completed"
- At the end, summarize the session (cards reviewed, performance distribution)

Begin by syncing and fetching the due cards for the "{deck_name}" deck."""

    # ========================================================================
    # DECK CONSOLIDATION
    # ========================================================================

    @mcp.prompt(
        name="deck_consolidation",
        description="Guide for merging and reorganizing Anki decks"
    )
    def deck_consolidation(source_decks: str = "", target_structure: str = "") -> str:
        return f"""You are helping the user consolidate and reorganize their Anki decks.

TASK: Merge or reorganize decks
- Source decks: {source_decks or "To be determined"}
- Target structure: {target_structure or "To be determined"}

WORKFLOW:
1. First, list all decks using list_decks with include_stats=true
2. Analyze the current deck structure and card distribution
3. Discuss with the user what they want to achieve:
   - Merge similar decks?
   - Create a better hierarchy?
   - Flatten nested decks?
   - Split a large deck?

4. Before making changes:
   - Use createBackup to backup the collection
   - Summarize the planned changes and get user confirmation

5. Execute the consolidation:
   - Use changeDeck to move cards between decks
   - Use renameDeck to rename decks if needed
   - Use deleteDeck to remove empty decks
   - Use create_deck for new target decks

6. After consolidation:
   - Show the new deck structure
   - Verify card counts match expectations
   - Sync to save changes

IMPORTANT:
- Always backup before making bulk changes
- Preserve tags - they provide additional organization
- Consider using filtered decks for temporary groupings
- Moving cards between decks doesn't affect their learning progress
- Parent::Child notation creates hierarchical decks"""

    # ========================================================================
    # CARD IMPROVEMENT
    # ========================================================================

    @mcp.prompt(
        name="card_improvement",
        description="Guide for analyzing and improving card quality"
    )
    def card_improvement(deck_name: str = "", focus_area: str = "all") -> str:
        return f"""You are helping the user improve the quality of their Anki cards.

ANALYSIS TARGET:
- Deck: {deck_name or "All decks"}
- Focus: {focus_area}

STEP 1: IDENTIFY PROBLEM CARDS
Use these tools to find cards needing improvement:
- getLeechCards: Find cards that are frequently forgotten
- getDifficultyDistribution: Find very hard cards
- getEmptyCards: Find notes with template issues
- findDuplicates: Find redundant content

STEP 2: ANALYZE CARD QUALITY
For each problem card, check for common issues:

BAD CARD PATTERNS:
- Too much information on one card
- Ambiguous questions with multiple valid answers
- Missing context that aids recall
- Poor formatting or hard-to-read content
- Over-reliance on recognition vs. recall

GOOD CARD PATTERNS:
- One fact per card (atomic)
- Clear, unambiguous questions
- Appropriate context without giving away answers
- Good use of cloze deletions for fill-in-the-blank
- Images and mnemonics where helpful

STEP 3: SUGGEST IMPROVEMENTS
For each problem card:
1. Show the current question and answer
2. Explain what's wrong
3. Suggest a specific improvement
4. Ask user for approval before changes

STEP 4: IMPLEMENT CHANGES
- Use updateNoteFields to modify card content
- Use addNote to create split cards from overloaded ones
- Use deleteNotes (with confirmation) to remove truly problematic cards
- Use updateNoteTags to mark cards as reviewed/improved

TIPS:
- The "minimum information principle" - smaller cards are easier to remember
- Use cloze deletions for lists and sequences
- Add personal connections and mnemonics
- Include images for concrete concepts"""

    # ========================================================================
    # LEECH REMEDIATION
    # ========================================================================

    @mcp.prompt(
        name="leech_remediation",
        description="Strategy for handling difficult/leech cards"
    )
    def leech_remediation(deck_name: str = "", threshold: int = 8) -> str:
        return f"""You are helping the user deal with leech cards - cards they keep forgetting.

PARAMETERS:
- Deck: {deck_name or "All decks"}
- Leech threshold: {threshold} lapses

STEP 1: FIND LEECHES
Use getLeechCards with threshold={threshold} to find problem cards.

STEP 2: CATEGORIZE LEECHES
For each leech, determine the likely cause:

A. CONTENT ISSUES:
- Card is too complex → Split into multiple cards
- Question is ambiguous → Rewrite clearly
- Answer is hard to remember → Add mnemonic

B. KNOWLEDGE GAPS:
- Missing prerequisite knowledge → Create foundational cards first
- Topic needs deeper understanding → Study the subject more

C. INTERFERENCE:
- Similar cards causing confusion → Differentiate them
- Too many similar items → Space out new additions

D. RELEVANCE:
- Material not useful → Consider suspending or deleting
- Outdated information → Update or remove

STEP 3: REMEDIATION ACTIONS
For each leech, choose an action:
1. REWRITE: Use updateNoteFields to improve the card
2. SPLIT: Create multiple simpler cards with addNote
3. SUSPEND: Use suspendCards to remove from rotation temporarily
4. DELETE: Use deleteNotes (with confirmation) for truly unhelpful cards
5. TAG: Use updateNoteTags to mark for later review

STEP 4: PREVENT FUTURE LEECHES
Suggest improvements to card creation habits:
- Follow the minimum information principle
- Add mnemonics proactively
- Use cloze deletions for complex information
- Test new cards before committing to them

After remediation, the user should notice:
- Fewer frustrating review sessions
- Better retention of material
- More enjoyable study experience"""

    # ========================================================================
    # STUDY PLANNING
    # ========================================================================

    @mcp.prompt(
        name="study_planning",
        description="Help create and optimize a study schedule"
    )
    def study_planning(goals: str = "", time_available: str = "") -> str:
        return f"""You are helping the user create an effective study plan.

USER GOALS: {goals or "To be discussed"}
TIME AVAILABLE: {time_available or "To be discussed"}

STEP 1: ASSESS CURRENT STATE
Use these tools to understand the user's situation:
- list_decks: See all decks and their sizes
- getDeckDueTree: See pending reviews
- getForecast: See upcoming workload
- getStudiedToday: See today's progress
- getRetentionAnalysis: Assess retention rates

STEP 2: UNDERSTAND GOALS
Discuss with the user:
- What are they learning and why?
- What's their deadline (if any)?
- How much time can they dedicate daily?
- Do they prefer long sessions or short bursts?

STEP 3: CREATE A PLAN

DAILY ROUTINE:
- Set realistic daily card limits (new + reviews)
- Schedule consistent study times
- Account for review backlog growth

DECK STRATEGY:
- Prioritize decks based on importance/deadline
- Consider deck-specific daily limits
- Plan for new card introduction rate

WORKLOAD MANAGEMENT:
- Use extendLimits for extra study sessions
- Use createCustomStudy for focused practice
- Monitor with getForecast to avoid review pile-up

STEP 4: IMPLEMENT THE PLAN
- Adjust deck configurations if needed
- Set up filtered decks for focused study
- Create reminders or habits

STUDY TIPS:
- Consistency beats intensity (daily is better than weekly binges)
- Review in the morning when possible
- Keep sessions under 30-60 minutes for focus
- New cards are harder than reviews - plan accordingly
- If falling behind, pause new cards until caught up"""

    # ========================================================================
    # NOTE CREATION
    # ========================================================================

    @mcp.prompt(
        name="note_creation",
        description="Best practices for creating effective Anki notes"
    )
    def note_creation(topic: str = "", note_type: str = "Basic") -> str:
        return f"""You are helping the user create effective Anki notes.

TOPIC: {topic or "To be specified"}
NOTE TYPE: {note_type}

PREPARATION:
1. Use modelNames to see available note types
2. Use modelFieldNames to see required fields for "{note_type}"
3. Use list_decks to find or create the target deck

PRINCIPLES OF GOOD CARDS:

1. MINIMUM INFORMATION
- One fact per card
- Bad: "What are the three states of matter?" (too complex)
- Good: Three separate cards, one per state

2. OPTIMIZED WORDING
- Simple, unambiguous questions
- No "What is X?" when "Define X" or specific question works better

3. CONTEXT CUES
- Include enough context to understand the question
- But don't give away the answer

4. USE CLOZE DELETIONS FOR:
- Fill-in-the-blank vocabulary
- Sequences and lists
- Formulas and definitions

5. ADD IMAGERY
- Use images for concrete concepts
- Store with storeMediaFile

6. PERSONAL CONNECTIONS
- Add mnemonics in extra fields
- Include why the information matters

CREATION WORKFLOW:
1. Draft the cards based on the topic
2. Show the user for review
3. Use addNote or addNotes to create them
4. Use updateNoteTags to organize

COMMON NOTE TYPES:
- Basic: Front/Back
- Basic (and reversed): Creates two cards
- Cloze: Fill-in-the-blank with {{{{c1::text}}}}
- Image Occlusion: Hide parts of images

After creation:
- Review the new cards to verify they work
- Consider using a filtered deck to preview before learning"""

    # ========================================================================
    # COLLECTION CLEANUP
    # ========================================================================

    @mcp.prompt(
        name="collection_cleanup",
        description="Guide for maintaining and optimizing the collection"
    )
    def collection_cleanup() -> str:
        return """You are helping the user clean up and optimize their Anki collection.

STEP 1: BACKUP FIRST
Always start with createBackup - collection maintenance can be destructive!

STEP 2: DATABASE HEALTH
- Use checkIntegrity to check for corruption
- Use optimizeDatabase to vacuum and analyze
- Report any issues found

STEP 3: FIND PROBLEMS
Use these tools to identify issues:
- getEmptyCards: Notes that don't generate cards
- findDuplicates: Redundant notes
- checkMedia: Missing or unused media files
- getLeechCards: Cards that need attention

STEP 4: CLEANUP ACTIONS

EMPTY CARDS/NOTES:
- Review why they're empty (template issues?)
- Delete with delete-empty-notes or fix the templates

DUPLICATES:
- Compare the duplicates
- Keep the better version, delete others
- Or merge information into one

MEDIA FILES:
- Missing: Find and restore, or update cards
- Unused: Consider deleting to save space

ORPHANED TAGS:
- Use clearUnusedTags to remove unused tags
- Clean up tag hierarchy

STEP 5: ORGANIZATION
- Consider consolidating small/scattered decks
- Review deck hierarchy
- Clean up tags for consistency

STEP 6: FINAL CHECKS
- Run checkIntegrity again
- Sync to save changes
- Verify collection size/performance

MAINTENANCE SCHEDULE RECOMMENDATION:
- Weekly: Quick check for issues
- Monthly: Full cleanup
- Before major changes: Always backup"""

    # ========================================================================
    # CLOZE CREATION
    # ========================================================================

    @mcp.prompt(
        name="cloze_creation",
        description="Guide for creating effective cloze deletion cards"
    )
    def cloze_creation(content: str = "", strategy: str = "standard") -> str:
        return f"""You are helping the user create cloze deletion cards.

CONTENT TO CONVERT: {content or "To be provided"}
STRATEGY: {strategy}

CLOZE SYNTAX:
- {{{{c1::text}}}} - First cloze (hidden)
- {{{{c2::text}}}} - Second cloze (separate card)
- {{{{c1::text::hint}}}} - With hint shown

STRATEGIES:

STANDARD (one card per cloze):
Each cloze number creates a separate card.
"The {{{{c1::mitochondria}}}} is the {{{{c2::powerhouse}}}} of the cell."
→ Creates 2 cards

OVERLAPPING (show related items):
Same cloze number hides together.
"{{{{c1::ATP}}}} is produced in the {{{{c1::mitochondria}}}}"
→ Creates 1 card, both hidden

ENUMERATION (lists/sequences):
"The three primary colors are {{{{c1::red}}}}, {{{{c2::blue}}}}, and {{{{c3::yellow}}}}"
→ Creates 3 cards, one per color

BEST PRACTICES:
1. Focus on key facts, not filler words
2. Include enough context to understand
3. Use hints for disambiguation: {{{{c1::word::first letter is M}}}}
4. Don't over-cloze - too many deletions = too hard
5. Test the cards to make sure they make sense

CREATION WORKFLOW:
1. Use modelFieldNames for "Cloze" to see required fields
2. Convert content to cloze format
3. Show user for approval
4. Use addNote with modelName="Cloze"

COMMON PATTERNS:
- Vocabulary: "{{{{c1::bonjour}}}} means {{{{c2::hello}}}} in French"
- Definitions: "{{{{c1::Photosynthesis}}}} is the process by which plants convert sunlight to energy"
- Formulas: "E = {{{{c1::mc²}}}}"
- Dates: "World War II ended in {{{{c1::1945}}}}"
- Sequences: "The order is: {{{{c1::First}}}}, {{{{c2::Second}}}}, {{{{c3::Third}}}}" """

    # ========================================================================
    # LANGUAGE LEARNING
    # ========================================================================

    @mcp.prompt(
        name="language_learning",
        description="Specialized guide for language learning cards"
    )
    def language_learning(target_language: str = "", native_language: str = "English") -> str:
        return f"""You are helping the user learn {target_language or "a new language"} with Anki.

TARGET LANGUAGE: {target_language or "To be specified"}
NATIVE LANGUAGE: {native_language}

CARD TYPES FOR LANGUAGE LEARNING:

1. VOCABULARY
- Recognition: Show word → recall meaning
- Production: Show meaning → recall word
- Use "Basic (and reversed)" for both directions
- Include: pronunciation, example sentence, image

2. SENTENCES
- Cloze deletions for grammar patterns
- Full sentence translation cards
- Audio whenever possible

3. GRAMMAR
- Pattern cards with cloze: "Je {{{{c1::suis}}}} content" (I am happy)
- Conjugation tables as separate cards
- Exception cards for irregular forms

RECOMMENDED NOTE STRUCTURE:
- Front: Target language word/phrase
- Back: Translation, pronunciation, example
- Extra: Mnemonic, related words, notes

CREATING EFFECTIVE LANGUAGE CARDS:

1. CONTEXT IS KING
- Include example sentences
- Show the word in use
- Add images for concrete nouns

2. AUDIO SUPPORT
- Use storeMediaFile for pronunciation
- Include native speaker recordings when possible
- Reference: Forvo, Google Translate TTS

3. SPACED REPETITION STRATEGIES
- Start with high-frequency words
- Add words from real content you're consuming
- Use tags: #beginner, #intermediate, #advanced

4. AVOID COMMON MISTAKES
- Don't learn words in isolation
- Don't use single-word translations (use phrases)
- Don't ignore pronunciation

WORKFLOW:
1. Identify words/phrases to learn
2. Create cards with context and audio
3. Use addNote with appropriate model
4. Tag by topic, difficulty, source
5. Review with special attention to production cards

DECK ORGANIZATION:
- By level: Beginner/Intermediate/Advanced
- By topic: Food, Travel, Business
- By source: Book name, Course name"""
