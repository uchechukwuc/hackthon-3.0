document.addEventListener('DOMContentLoaded', () => {
    // Check if the main app elements exist before adding listeners
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        // --- DOM Element References ---
        const notesInput = document.getElementById('notes-input');
        const flashcardContainer = document.getElementById('flashcard-container');
        const statusMessage = document.getElementById('status-message');
        const creditsDisplay = document.getElementById('credits-display');

        const setLoadingState = (isLoading) => {
            generateBtn.disabled = isLoading;
            if (isLoading) {
                statusMessage.textContent = 'Generating your flashcards... This may take a moment. 🧠';
                generateBtn.textContent = 'Working...';
            } else {
                statusMessage.textContent = '';
                generateBtn.textContent = 'Generate Flashcards (1 Credit)';
            }
        };
        
        const createFlashcardElement = (question, answer) => {
            // This function is unchanged, copy from previous version
            const card = document.createElement('div');
            card.className = 'flashcard';
            const cardInner = document.createElement('div');
            cardInner.className = 'flashcard-inner';
            const cardFront = document.createElement('div');
            cardFront.className = 'flashcard-front';
            cardFront.innerHTML = `<span class="flashcard-label">Question</span><p>${question}</p>`;
            const cardBack = document.createElement('div');
            cardBack.className = 'flashcard-back';
            cardBack.innerHTML = `<span class="flashcard-label">Answer</span><p>${answer}</p>`;
            cardInner.appendChild(cardFront);
            cardInner.appendChild(cardBack);
            card.appendChild(cardInner);
            card.addEventListener('click', () => card.classList.toggle('is-flipped'));
            return card;
        };

        const handleGenerateClick = async () => {
            const notesText = notesInput.value.trim();
            if (!notesText) {
                statusMessage.textContent = 'Please paste some notes first!';
                return;
            }

            setLoadingState(true);
            flashcardContainer.innerHTML = '';

            try {
                const response = await fetch('/generate-flashcards', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ text: notesText }),
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || `HTTP error! Status: ${response.status}`);
                }
                
                // Update credits display on success
                const currentCredits = parseInt(creditsDisplay.textContent, 10);
                if (!isNaN(currentCredits)) {
                    creditsDisplay.textContent = currentCredits - 1;
                }

                if (data.length === 0) {
                    statusMessage.textContent = 'Could not generate flashcards. Please try again.';
                } else {
                    data.forEach(card => {
                        const cardElement = createFlashcardElement(card.question, card.answer);
                        flashcardContainer.appendChild(cardElement);
                    });
                }
            } catch (error) {
                console.error('Error fetching flashcards:', error);
                statusMessage.textContent = `An error occurred: ${error.message}`;
            } finally {
                setLoadingState(false);
            }
        };

        generateBtn.addEventListener('click', handleGenerateClick);
    }
    
    // --- Stripe Payment Logic ---
    const buyCreditsBtn = document.getElementById('buy-credits-btn');
    if (buyCreditsBtn) {
        buyCreditsBtn.addEventListener('click', async () => {
            try {
                // 1. Get Stripe Publishable Key from our server
                const configResponse = await fetch('/config');
                const { publishableKey } = await configResponse.json();
                const stripe = Stripe(publishableKey);

                // 2. Create a Checkout Session on our server
                const sessionResponse = await fetch('/create-checkout-session', { method: 'POST' });
                const { sessionId } = await sessionResponse.json();

                // 3. Redirect to Stripe Checkout
                const { error } = await stripe.redirectToCheckout({ sessionId });
                if (error) {
                    console.error('Stripe redirect error:', error);
                    alert(error.message);
                }
            } catch (error) {
                console.error('Payment initiation error:', error);
            }
        });
    }
});