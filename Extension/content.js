// AI Tab Organizer - Content Script
// This script runs on each webpage to help extract content

// Function to extract detailed page content
function extractPageContent() {
  try {
    return {
      // Basic page info
      title: document.title,
      url: window.location.href,
      domain: window.location.hostname,
      
      // Meta information
      description: getMetaContent('description'),
      keywords: getMetaContent('keywords'),
      author: getMetaContent('author'),
      
      // Content analysis
      headings: extractHeadings(),
      mainContent: extractMainContent(),
      linkCount: document.links.length,
      imageCount: document.images.length,
      
      // Page characteristics
      wordCount: getWordCount(),
      language: document.documentElement.lang || 'unknown',
      lastModified: document.lastModified,
      
      // Social media and article info
      articleAuthor: getArticleAuthor(),
      publishDate: getPublishDate(),
      socialLinks: getSocialLinks(),
      
      // Page activity indicators
      hasComments: hasCommentsSection(),
      hasVideo: hasVideoContent(),
      hasForm: document.forms.length > 0,
      
      // Content type detection
      pageType: detectPageType(),
      
      // Scroll and interaction data
      scrollPosition: window.pageYOffset,
      documentHeight: document.documentElement.scrollHeight,
      viewportHeight: window.innerHeight
    };
  } catch (error) {
    console.error('Error extracting page content:', error);
    return {
      title: document.title,
      url: window.location.href,
      error: 'Content extraction failed'
    };
  }
}

// Helper function to get meta content
function getMetaContent(name) {
  const meta = document.querySelector(`meta[name="${name}"], meta[property="og:${name}"], meta[property="twitter:${name}"]`);
  return meta ? meta.content : '';
}

// Extract headings from the page
function extractHeadings() {
  const headings = [];
  const headingElements = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
  
  headingElements.forEach((heading, index) => {
    if (index < 10) { // Limit to first 10 headings
      headings.push({
        level: parseInt(heading.tagName.charAt(1)),
        text: heading.textContent.trim().substring(0, 100)
      });
    }
  });
  
  return headings;
}

// Extract main content (try to find article or main content area)
function extractMainContent() {
  let mainText = '';
  
  // Try to find main content areas
  const contentSelectors = [
    'article',
    'main',
    '.content',
    '#content',
    '.post',
    '.entry-content',
    '.article-content',
    '.story-body'
  ];
  
  for (const selector of contentSelectors) {
    const element = document.querySelector(selector);
    if (element) {
      mainText = element.textContent.trim().substring(0, 1500);
      break;
    }
  }
  
  // Fallback to body text if no specific content area found
  if (!mainText) {
    mainText = document.body.textContent.trim().substring(0, 1500);
  }
  
  return mainText;
}

// Get word count of the page
function getWordCount() {
  const text = document.body.textContent || '';
  const words = text.trim().split(/\s+/).filter(word => word.length > 0);
  return words.length;
}

// Try to detect article author
function getArticleAuthor() {
  const authorSelectors = [
    '.author',
    '.byline',
    '.writer',
    '[rel="author"]',
    '.article-author',
    '.post-author'
  ];
  
  for (const selector of authorSelectors) {
    const element = document.querySelector(selector);
    if (element) {
      return element.textContent.trim().substring(0, 50);
    }
  }
  
  return getMetaContent('author');
}

// Try to detect publish date
function getPublishDate() {
  const dateSelectors = [
    'time[datetime]',
    '.date',
    '.publish-date',
    '.article-date',
    '.post-date'
  ];
  
  for (const selector of dateSelectors) {
    const element = document.querySelector(selector);
    if (element) {
      return element.getAttribute('datetime') || element.textContent.trim();
    }
  }
  
  return '';
}

// Find social media links
function getSocialLinks() {
  const socialDomains = ['twitter.com', 'facebook.com', 'linkedin.com', 'instagram.com', 'youtube.com'];
  const socialLinks = [];
  
  document.querySelectorAll('a[href]').forEach(link => {
    const href = link.href;
    for (const domain of socialDomains) {
      if (href.includes(domain)) {
        socialLinks.push(domain.split('.')[0]);
        break;
      }
    }
  });
  
  return [...new Set(socialLinks)]; // Remove duplicates
}

// Check if page has comments section
function hasCommentsSection() {
  const commentSelectors = [
    '.comments',
    '#comments',
    '.comment-section',
    '.disqus',
    '[id*="comment"]',
    '[class*="comment"]'
  ];
  
  return commentSelectors.some(selector => document.querySelector(selector));
}

// Check if page has video content
function hasVideoContent() {
  return document.querySelectorAll('video, iframe[src*="youtube"], iframe[src*="vimeo"]').length > 0;
}

// Detect page type based on content and structure
function detectPageType() {
  const url = window.location.href.toLowerCase();
  const title = document.title.toLowerCase();
  const bodyText = document.body.textContent.toLowerCase();
  
  // E-commerce
  if (url.includes('/cart') || url.includes('/checkout') || 
      bodyText.includes('add to cart') || bodyText.includes('buy now')) {
    return 'ecommerce';
  }
  
  // Social media
  if (url.includes('facebook.com') || url.includes('twitter.com') || 
      url.includes('instagram.com') || url.includes('linkedin.com')) {
    return 'social';
  }
  
  // News/Article
  if (document.querySelector('article') || 
      title.includes('news') || 
      getArticleAuthor() || 
      getPublishDate()) {
    return 'article';
  }
  
  // Video
  if (url.includes('youtube.com') || url.includes('vimeo.com') || 
      hasVideoContent()) {
    return 'video';
  }
  
  // Documentation/Reference
  if (url.includes('docs.') || url.includes('documentation') || 
      title.includes('documentation') || title.includes('reference')) {
    return 'documentation';
  }
  
  // Search results
  if (url.includes('search') || url.includes('/s?') || 
      document.querySelector('.search-results')) {
    return 'search';
  }
  
  // Development/Code
  if (url.includes('github.com') || url.includes('stackoverflow.com') || 
      document.querySelector('code, pre')) {
    return 'development';
  }
  
  return 'general';
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getPageContent') {
    const content = extractPageContent();
    sendResponse(content);
  }
});

// Track page interaction (scroll, time spent)
let pageLoadTime = Date.now();
let maxScrollDepth = 0;
let interactionCount = 0;

// Track scroll depth
window.addEventListener('scroll', () => {
  const scrollPercent = (window.pageYOffset / (document.documentElement.scrollHeight - window.innerHeight)) * 100;
  maxScrollDepth = Math.max(maxScrollDepth, scrollPercent);
});

// Track interactions
['click', 'keydown', 'mousedown'].forEach(eventType => {
  document.addEventListener(eventType, () => {
    interactionCount++;
  }, { passive: true });
});

// Function to get engagement metrics
function getEngagementMetrics() {
  return {
    timeOnPage: Date.now() - pageLoadTime,
    maxScrollDepth: Math.round(maxScrollDepth),
    interactionCount: interactionCount,
    hasInteracted: interactionCount > 0
  };
}

// Make engagement metrics available to background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getEngagementMetrics') {
    sendResponse(getEngagementMetrics());
  }
});
