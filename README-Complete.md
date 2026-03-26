# 🚀 Claude Skills Integration Kit

Complete guide to integrating Claude AI capabilities into your projects.

---

## 📋 What You Get

This kit includes everything needed to:

✅ **Development**: Test Claude skills locally  
✅ **Integration**: Use skills in your application  
✅ **Production**: Deploy to any server  
✅ **Modularity**: Pick only the skills you need  
✅ **Flexibility**: Works with Node.js or Python  

---

## ⚡ Quick Start (5 Minutes)

### 1. Get API Key
```bash
# Visit: https://console.anthropic.com
# Create API key, copy it (starts with 'sk-ant-')
```

### 2. Choose Your Path

#### **Option A: Node.js**
```bash
# Create project
mkdir claude-app && cd claude-app

# Create .env file
echo "CLAUDE_API_KEY=sk-ant-YOUR-KEY-HERE" > .env

# Copy all nodejs boilerplate files to your project
# Install dependencies
npm install @anthropic-ai/sdk dotenv express

# Test
node examples/3-testing-local.js
```

#### **Option B: Python**
```bash
# Create project
mkdir claude-app && cd claude-app

# Create .env file
echo "CLAUDE_API_KEY=sk-ant-YOUR-KEY-HERE" > .env

# Install dependencies
pip install anthropic python-dotenv flask

# Test
python examples/basic_usage.py
```

---

## 📁 Files Provided

### **Documentation**
- `claude-skills-setup-guide.md` - Comprehensive setup guide
- `README.md` - This file

### **Node.js Boilerplate** (Choose one)
- `nodejs-boilerplate-api.config.js` - API configuration
- `nodejs-boilerplate-base-skill.js` - Base skill class
- `nodejs-boilerplate-all-skills.js` - All skill implementations
- `nodejs-boilerplate-index.js` - Main export/index
- `nodejs-boilerplate-examples.js` - 3 complete examples
- `nodejs-setup-package-env.json` - package.json + .env setup

### **Python Boilerplate**
- `python-boilerplate-complete.py` - All Python skills + examples

---

## 🎯 Available Skills

### 1. **Sales Skill**
```javascript
// Analyze prospects
await skills.sales.analyzeProspect(prospectData)

// Generate pitches
await skills.sales.generatePitch(product, audience)

// Handle objections
await skills.sales.handleObjection(objection, context)
```

### 2. **Productivity Skill**
```javascript
// Prioritize tasks
await skills.productivity.prioritizeTasks(taskList)

// Create project plans
await skills.productivity.createProjectPlan(project)
```

### 3. **Finance Skill**
```javascript
// Analyze financials
await skills.finance.analyzeFinancials(data)

// Create budgets
await skills.finance.createBudget(context)
```

### 4. **Marketing Skill**
```javascript
// Campaign strategy
await skills.marketing.createCampaignStrategy(product)

// Generate copy
await skills.marketing.generateMarketingCopy(context)
```

### 5. **Engineering Skill**
```javascript
// Code review
await skills.engineering.reviewCode(code, context)

// Design architecture
await skills.engineering.designArchitecture(requirements)
```

---

## 💻 Usage Examples

### In Development (Node.js)

```javascript
const { skills } = require('./claude-skills');

// Quick example
async function demo() {
  const pitch = await skills.sales.generatePitch(
    { name: 'MyProduct', price: '$99/mo' },
    { role: 'CTO', industry: 'SaaS' }
  );
  console.log(pitch);
}

demo();
```

### In Your Application (Express)

```javascript
const express = require('express');
const { skills } = require('./claude-skills');

const app = express();
app.use(express.json());

app.post('/api/analyze-prospect', async (req, res) => {
  try {
    const analysis = await skills.sales.analyzeProspect(req.body);
    res.json({ success: true, analysis });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.listen(3000);
```

### In Your Application (Python/Flask)

```python
from flask import Flask, request, jsonify
from claude_skills import sales

app = Flask(__name__)

@app.route('/api/analyze-prospect', methods=['POST'])
def analyze_prospect():
    try:
        data = request.json
        analysis = sales.analyze_prospect(data)
        return jsonify({'success': True, 'analysis': analysis})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run()
```

---

## 🔧 Project Structure

```
your-project/
├── claude-skills/
│   ├── config/
│   │   └── api.config.js
│   ├── skills/
│   │   ├── base-skill.js
│   │   ├── sales.js
│   │   ├── productivity.js
│   │   ├── finance.js
│   │   ├── marketing.js
│   │   └── engineering.js
│   └── index.js
├── examples/
│   ├── 1-basic-usage.js
│   ├── 2-in-application.js
│   └── 3-testing-local.js
├── src/
│   ├── api/
│   └── routes/
├── .env
├── package.json
└── README.md
```

---

## 🚀 Deployment

### To Heroku
```bash
# Add buildpacks
heroku buildpacks:add heroku/nodejs

# Set environment
heroku config:set CLAUDE_API_KEY=sk-ant-xxx

# Deploy
git push heroku main
```

### To Vercel (Serverless)
```bash
# Add env var in Vercel dashboard
CLAUDE_API_KEY=sk-ant-xxx

# Deploy
vercel
```

### To AWS Lambda
```bash
# Install serverless
npm install -g serverless

# Deploy
serverless deploy --param="CLAUDE_API_KEY=sk-ant-xxx"
```

---

## 🔐 Security Best Practices

1. **Never commit API keys**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use environment variables**
   ```javascript
   const apiKey = process.env.CLAUDE_API_KEY;
   ```

3. **Rate limit API calls**
   ```javascript
   // Add rate limiting middleware
   const rateLimit = require('express-rate-limit');
   const limiter = rateLimit({
     windowMs: 60 * 1000, // 1 minute
     max: 30 // 30 requests per minute
   });
   app.use(limiter);
   ```

4. **Validate input**
   ```javascript
   // Always validate user input before sending to Claude
   if (!req.body.prospect || !req.body.prospect.name) {
     return res.status(400).json({ error: 'Invalid input' });
   }
   ```

---

## 📊 API Rate Limits

Claude API has the following limits:
- **Rate**: Varies by model and plan
- **Token limit**: 128K context window
- **Max output**: 4K tokens per request

**Recommendation**: Implement exponential backoff for retries

```javascript
async function executeWithRetry(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      const delay = Math.pow(2, i) * 1000; // 1s, 2s, 4s
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

---

## 🧪 Testing

### Unit Test Example
```javascript
// test/sales.test.js
const { skills } = require('../claude-skills');

test('analyzeProspect returns analysis', async () => {
  const result = await skills.sales.analyzeProspect({
    name: 'Test Company',
    industry: 'Tech'
  });
  
  expect(result).toBeTruthy();
  expect(result).toContain('Lead Quality');
});
```

### Run Tests
```bash
npm test
# or
python -m pytest tests/
```

---

## 🐛 Troubleshooting

### API Key Issues
```
Error: 401 Unauthorized
→ Check CLAUDE_API_KEY in .env
→ Verify key hasn't been revoked
→ Get new key from console.anthropic.com
```

### Module Not Found
```
Error: Cannot find module '@anthropic-ai/sdk'
→ Run: npm install
→ Check node_modules/ exists
```

### Timeout Issues
```
Error: Request timeout
→ Increase timeout: client.messages.create({ ... }, { timeout: 60000 })
→ Check network connection
→ API might be slow (normal)
```

### JSON Parse Errors
```
Error: JSON parse error
→ Claude sometimes returns markdown code blocks
→ Use executeJSON() method which auto-cleans
→ Or manually: response.replace(/```json\n?|\n?```/g, '')
```

---

## 📈 Best Practices

### 1. Cache Results
```javascript
const cache = new Map();

async function analyzeWithCache(prospect) {
  const key = JSON.stringify(prospect);
  if (cache.has(key)) return cache.get(key);
  
  const result = await skills.sales.analyzeProspect(prospect);
  cache.set(key, result);
  return result;
}
```

### 2. Batch Operations
```javascript
// Don't do this - too many API calls
for (prospect of prospects) {
  await skills.sales.analyzeProspect(prospect);
}

// Do this - batch them
const analyses = await Promise.all(
  prospects.map(p => skills.sales.analyzeProspect(p))
);
```

### 3. Add Logging
```javascript
console.log('[Sales] Analyzing prospect:', prospect.name);
const start = Date.now();
const result = await skills.sales.analyzeProspect(prospect);
console.log(`[Sales] Completed in ${Date.now() - start}ms`);
```

### 4. Error Handling
```javascript
app.post('/api/analyze', async (req, res) => {
  try {
    const analysis = await skills.sales.analyzeProspect(req.body);
    res.json({ success: true, analysis });
  } catch (error) {
    console.error('Analysis failed:', error);
    
    // Send friendly error to client
    res.status(500).json({
      error: 'Analysis failed. Please try again.',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});
```

---

## 📚 Learning Resources

- **Claude API Docs**: https://docs.claude.com
- **Anthropic Discord**: https://discord.gg/anthropic
- **API Console**: https://console.anthropic.com
- **Model Information**: https://www.anthropic.com/pricing

---

## 🤝 Contributing

Found a bug or have a suggestion?

1. Test it locally
2. Document the issue
3. Submit a pull request

---

## 📄 License

MIT License - Feel free to use this in your projects!

---

## ✨ Next Steps

1. **Setup**: Follow the Quick Start section
2. **Test**: Run the examples provided
3. **Customize**: Modify skills for your needs
4. **Deploy**: Push to production
5. **Monitor**: Track usage and costs
6. **Iterate**: Improve prompts based on results

---

## 🎓 Tips for Best Results

### Good Prompts
- Be specific about what you want
- Provide context and examples
- Ask for structured output (JSON)
- Give clear instructions

### Example
```javascript
// ✅ GOOD
const pitch = await skills.sales.generatePitch(
  {
    name: 'CloudSync Pro',
    value_prop: 'Saves 10 hours/week on data entry',
    target_user: 'Operations Manager'
  },
  { industry: 'SaaS', company_size: '50 people' }
);

// ❌ AVOID
const pitch = await skills.sales.generatePitch(
  { product: 'Our app' },
  { target: 'people' }
);
```

---

## 💡 Ideas for Extension

- Add more skills (Customer Support, Product, etc.)
- Connect to your CRM (Salesforce, HubSpot)
- Integrate with Slack for notifications
- Build a dashboard to monitor skill usage
- Add fine-tuning for domain-specific knowledge

---

Happy building! 🚀

For questions or issues, check the comprehensive setup guide:  
`claude-skills-setup-guide.md`
