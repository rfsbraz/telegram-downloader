// Custom JavaScript for Telegram Downloader Documentation

document.addEventListener('DOMContentLoaded', function() {
  // Open external links in new tab
  const links = document.querySelectorAll('a[href^="http"]');
  links.forEach(link => {
    if (!link.hostname.includes(window.location.hostname)) {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    }
  });

  // Add copy feedback to code blocks
  document.querySelectorAll('.md-clipboard').forEach(button => {
    button.addEventListener('click', function() {
      const originalTitle = button.title;
      button.title = 'Copied!';
      setTimeout(() => {
        button.title = originalTitle;
      }, 2000);
    });
  });

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href !== '#') {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
          // Update URL without jumping
          history.pushState(null, '', href);
        }
      }
    });
  });

  // Add "Back to top" enhancement
  window.addEventListener('scroll', function() {
    const backToTop = document.querySelector('.md-top');
    if (backToTop) {
      if (window.pageYOffset > 300) {
        backToTop.style.opacity = '1';
      } else {
        backToTop.style.opacity = '0.5';
      }
    }
  });

  // Analytics (optional - uncomment if needed)
  /*
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
  */
});
