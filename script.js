// Copy product code functionality
function copyCode(code) {
    // Copy to clipboard
    navigator.clipboard.writeText(code).then(() => {
        // Show toast notification
        showToast('Kód zkopírován! 📋');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showToast('Chyba při kopírování');
    });
}

// Show toast notification
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 2000);
}

// Smooth scroll for TOC links
document.addEventListener('DOMContentLoaded', () => {
    // Smooth scrolling for all anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Highlight active section in TOC
    const sections = document.querySelectorAll('.content-section');
    const tocLinks = document.querySelectorAll('.toc a');

    const observerOptions = {
        root: null,
        rootMargin: '-100px 0px -80% 0px',
        threshold: 0
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                tocLinks.forEach(link => {
                    link.style.color = '';
                    link.style.fontWeight = '';
                    if (link.getAttribute('href') === `#${id}`) {
                        link.style.color = '#E89B8A';
                        link.style.fontWeight = 'bold';
                    }
                });
            }
        });
    }, observerOptions);

    sections.forEach(section => {
        observer.observe(section);
    });

    // Add fade-in animation to ingredient cards on scroll
    const cards = document.querySelectorAll('.ingredient-card');

    const cardObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }, index * 100);
                cardObserver.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1
    });

    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        cardObserver.observe(card);
    });

    // Add reading progress bar
    createProgressBar();

    // Mobile menu toggle (if needed in future)
    const header = document.querySelector('.header');
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;

        // Auto-hide header on scroll down (optional)
        if (currentScroll > lastScroll && currentScroll > 100) {
            header.style.transform = 'translateY(-100%)';
        } else {
            header.style.transform = 'translateY(0)';
        }

        lastScroll = currentScroll;

        // Update progress bar
        updateProgressBar();
    });
});

// Create reading progress bar
function createProgressBar() {
    const progressBar = document.createElement('div');
    progressBar.id = 'reading-progress';
    progressBar.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 0%;
        height: 3px;
        background: linear-gradient(90deg, #E89B8A 0%, #C77B68 100%);
        z-index: 9999;
        transition: width 0.1s ease;
    `;
    document.body.appendChild(progressBar);
}

// Update reading progress bar
function updateProgressBar() {
    const progressBar = document.getElementById('reading-progress');
    const windowHeight = window.innerHeight;
    const documentHeight = document.documentElement.scrollHeight - windowHeight;
    const scrolled = window.pageYOffset;
    const progress = (scrolled / documentHeight) * 100;

    if (progressBar) {
        progressBar.style.width = progress + '%';
    }
}

// Add hover effect to product links
document.querySelectorAll('.product-link').forEach(link => {
    link.addEventListener('mouseenter', function() {
        this.style.transform = 'translateX(5px)';
    });

    link.addEventListener('mouseleave', function() {
        this.style.transform = 'translateX(0)';
    });
});

// Add click tracking for analytics (placeholder)
function trackClick(elementType, elementId) {
    console.log(`Tracked: ${elementType} - ${elementId}`);
    // Here you would integrate with Google Analytics, Matomo, etc.
    // Example: gtag('event', 'click', { element_type: elementType, element_id: elementId });
}

// Track CTA button clicks
document.querySelectorAll('.cta-primary, .cta-secondary').forEach(button => {
    button.addEventListener('click', () => {
        trackClick('CTA Button', button.textContent);
    });
});

// Track product code copies
const originalCopyCode = copyCode;
copyCode = function(code) {
    trackClick('Product Code Copy', code);
    originalCopyCode(code);
};

// Lazy load images (if you add actual images later)
function lazyLoadImages() {
    const images = document.querySelectorAll('img[data-src]');

    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
}

// Initialize on load
window.addEventListener('load', () => {
    lazyLoadImages();
});

// Add keyboard navigation support
document.addEventListener('keydown', (e) => {
    // Press 'T' to scroll to top
    if (e.key === 't' || e.key === 'T') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Press 'B' to scroll to bottom
    if (e.key === 'b' || e.key === 'B') {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
});

// Print functionality
function printArticle() {
    window.print();
}

// Share functionality (Web Share API)
function shareArticle() {
    if (navigator.share) {
        navigator.share({
            title: document.title,
            text: 'Podívejte se na tento skvělý článek o péči o pleť!',
            url: window.location.href
        }).then(() => {
            showToast('Článek sdílen! 🎉');
        }).catch((error) => {
            console.log('Error sharing:', error);
        });
    } else {
        // Fallback: copy URL to clipboard
        copyCode(window.location.href);
        showToast('URL zkopírována! 🔗');
    }
}

// Add share buttons dynamically (optional)
function addShareButtons() {
    const conclusion = document.querySelector('.conclusion-section');
    if (conclusion) {
        const shareDiv = document.createElement('div');
        shareDiv.style.cssText = 'text-align: center; margin: 2rem 0;';
        shareDiv.innerHTML = `
            <button onclick="shareArticle()" style="
                background: #7BA687;
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 25px;
                cursor: pointer;
                font-weight: 600;
                margin: 0 0.5rem;
            ">📤 Sdílet článek</button>
            <button onclick="printArticle()" style="
                background: #E89B8A;
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 25px;
                cursor: pointer;
                font-weight: 600;
                margin: 0 0.5rem;
            ">🖨️ Vytisknout</button>
        `;
        conclusion.insertBefore(shareDiv, conclusion.firstChild);
    }
}

// Uncomment to enable share buttons
// addShareButtons();

// Console message for developers
console.log('%c👋 Ahoj!', 'font-size: 20px; color: #E89B8A; font-weight: bold;');
console.log('%cDěkujeme za zájem o náš web!', 'font-size: 14px; color: #666;');
console.log('%cJsme rádi, že si prohlížíte náš kód 🎨', 'font-size: 12px; color: #999;');