# AI Tab Organizer Chrome Extension

A powerful Chrome extension that uses OpenAI's GPT-4.1 to intelligently organize and manage your browser tabs.

## 🚀 Features

- **AI-Powered Analysis**: Uses GPT-4.1 to analyze tab content and importance
- **Smart Tab Closing**: Automatically closes tabs below your importance threshold
- **Intelligent Grouping**: Organizes remaining tabs into logical groups by topic
- **Debug Tools**: Create test tabs and manage all tabs for testing
- **Customizable Settings**: Adjust importance threshold and auto-close behavior

## 📋 Installation

1. Download or clone this extension
2. Open Chrome and go to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top right)
4. Click "Load unpacked" and select the Extension folder
5. Pin the extension to your toolbar

## ⚙️ Setup

1. **Get OpenAI API Key**:
   - Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
   - Create a new API key
   - Copy the key (starts with `sk-`)

2. **Configure Extension**:
   - Click the extension icon in your toolbar
   - Paste your API key in the settings
   - Adjust importance threshold (1-10 scale)
   - Enable auto-close if desired

## 🎯 How to Use

### Basic Usage
1. **Open the extension popup** by clicking the icon
2. **Enter your OpenAI API key** in the settings
3. **Set your importance threshold** (tabs below this score will be closed)
4. **Click "Organize & Clean Tabs"** to start the AI analysis

### Debug Tools
- **Create Test Tabs**: Generates random tabs for testing
- **Close All Tabs**: Closes all tabs except the current one (use with caution!)

### Keyboard Shortcuts
- `Ctrl/Cmd + Enter`: Organize tabs
- `Ctrl/Cmd + D`: Create debug tabs

## 🤖 How It Works

The extension follows this intelligent workflow:

1. **Tab Analysis**: Extracts content from all open tabs including:
   - Page titles and URLs
   - Meta descriptions and keywords
   - Main content and headings
   - Page type detection (article, social, ecommerce, etc.)

2. **AI Processing**: Sends tab data to GPT-4.1 which:
   - Rates each tab's importance (1-10 scale)
   - Considers content relevance, uniqueness, and value
   - Identifies tabs suitable for closing

3. **Smart Actions**:
   - **Closes** tabs below your importance threshold (if enabled)
   - **Groups** remaining tabs by topic with colored labels
   - **Organizes** your browser for better productivity

## 📊 Importance Scoring

The AI considers multiple factors when rating tab importance:

- **Content Quality**: Unique, valuable, or reference material
- **Recency**: Recently visited or active tabs
- **Page Type**: Documentation, articles, work-related content
- **User Activity**: Time spent, scroll depth, interactions
- **Uniqueness**: Hard-to-find or specialized information

## 🎨 Tab Grouping

Tabs are organized into logical groups such as:

- 🔍 **Research & Reference**
- 💼 **Work & Productivity**
- 📰 **News & Articles**
- 🛒 **Shopping & Commerce**
- 🎥 **Entertainment & Media**
- 👥 **Social & Communication**
- 💻 **Development & Tech**
- 📚 **Documentation & Learning**

## 🔧 Technical Details

### Files Structure
```
Extension/
├── manifest.json       # Extension configuration
├── background.js       # Main logic and API integration
├── content.js         # Page content extraction
├── popup.html         # User interface
├── popup.js          # UI interactions
└── README.md         # Documentation
```

### Permissions Required
- `tabs`: Read and manage browser tabs
- `tabGroups`: Create and organize tab groups
- `storage`: Save user settings and API key
- `activeTab`: Access current tab information
- `scripting`: Execute scripts for content extraction
- `<all_urls>`: Access page content for analysis

### API Integration
- Uses OpenAI GPT-4.1 model for intelligent analysis
- Respects API rate limits and handles errors gracefully
- Falls back to basic organization if API fails

## 🔐 Privacy & Security

- **API Key**: Stored locally in Chrome's sync storage, never shared
- **Tab Data**: Only sent to OpenAI for analysis, not stored permanently
- **Content**: Limited to 2000 characters per tab for privacy
- **No Tracking**: Extension doesn't collect or transmit personal data

## 🐛 Troubleshooting

### Common Issues

**Extension not working:**
- Ensure you're using Manifest V3 compatible Chrome version
- Check that all permissions are granted
- Verify API key is valid and starts with `sk-`

**API Errors:**
- Check your OpenAI account has available credits
- Verify API key permissions include GPT-4.1 access
- Check browser console for detailed error messages

**Tabs not closing:**
- Enable "Auto-close low importance tabs" in settings
- Lower the importance threshold
- Check that tabs aren't pinned (pinned tabs are preserved)

### Debug Mode
Enable debug mode in popup for detailed console logging:
1. Right-click extension icon → "Inspect popup"
2. Check Console tab for detailed logs
3. Monitor background script in Extensions page

## 📝 Version History

### v1.0.0
- Initial release
- GPT-4.1 integration for tab analysis
- Smart tab closing and grouping
- Debug tools for testing
- Responsive popup interface

## 🤝 Contributing

This extension was built as a proof of concept. Feel free to:
- Report bugs or suggestions
- Improve the AI prompts for better analysis
- Add new grouping categories
- Enhance the user interface

## 📄 License

This project is open source and available under the MIT License.

## ⚠️ Important Notes

- **API Costs**: Using GPT-4.1 incurs OpenAI API charges
- **Tab Limits**: Performance may vary with 50+ tabs
- **Permissions**: Extension requires broad permissions for full functionality
- **Data Usage**: Tab content is sent to OpenAI for analysis

---

**Made with ❤️ for better tab management**
