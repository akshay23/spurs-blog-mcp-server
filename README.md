## 📋 Overview

This MCP server connects to the Pounding The Rock (PTR) RSS feed and provides AI assistants with access to the latest Spurs game results and blog posts.

## 🛠️ Installation Guide

### Prerequisites
- 🐍 Python 3.13 or higher installed on your computer
- 💻 Basic familiarity with command line operations

### Step-by-Step Installation

<details open>
<summary><b>1️⃣ Get the code</b></summary>

```bash
# Clone with Git
git clone https://github.com/yourusername/spurs-blog-mcp-server.git
cd spurs-blog-mcp-server

# Or download the ZIP and extract it
```
</details>

<details open>
<summary><b>2️⃣ Install dependencies</b></summary>

```bash
# Install all required packages
pip install -r requirements.txt
```
</details>

<details open>
<summary><b>3️⃣ Launch the server</b></summary>

```bash
# Start the MCP server
python pounding_the_rock.py
```

> 💡 The server is running successfully when there is no error output. Keep this terminal window open while using the server with Claude.
</details>

## 🔄 Connecting to Claude for Desktop

### Setting up Claude Desktop

<details open>
<summary><b>1️⃣ Install Claude for Desktop</b></summary>

- Download from [claude.ai/download](https://claude.ai/download)
- Follow the installation instructions for your operating system
</details>

<details open>
<summary><b>2️⃣ Open the configuration file</b></summary>

**Mac users**:
1. Click on the Claude menu at the top of your screen
2. Select "Settings..."
3. Click on "Developer" in the left sidebar
4. Click "Edit Config"

**Windows users**:
1. Open File Explorer
2. Navigate to `%APPDATA%\Claude\`
3. Create or edit the file `claude_desktop_config.json`
</details>

<details open>
<summary><b>3️⃣ Add the server configuration</b></summary>

Copy and paste the following JSON into the configuration file:

```json
{
  "mcpServers": {
    "spurs-blog": {
      "command": "uv",
      "args": [
        "--directory",
        "/REPLACE/WITH/FULL/PATH/TO/spurs-blog-mcp-server/",
        "run",
        "pounding_the_rock.py"
      ]
    }
  }
}
```

> ⚠️ **Important**: Replace `/REPLACE/WITH/FULL/PATH/TO/spurs-blog-mcp-server/` with the actual full path to the server file on your computer.

<details open>
<summary><b>4️⃣ Finalize setup</b></summary>

1. Save the configuration file
2. Restart Claude for Desktop
3. **Verify connection**: Look for the 🔨 hammer icon in the bottom right of the chat interface, indicating available tools
</details>

## 👥 Contributing

Contributions are welcome! Feel free to submit pull requests or open issues if you have suggestions for improvements.

### Developer Resources

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://modelcontextprotocol.io/tutorials/building-mcp-with-llms">
          <img src="https://mintlify.s3.us-west-1.amazonaws.com/mcp/images/claude-desktop-mcp-plug-icon.svg" width="80" alt="MCP with LLMs"><br>
          <b>Building MCP with LLMs</b>
        </a>
      </td>
      <td align="center">
        <a href="https://modelcontextprotocol.io/docs/concepts/architecture">
          <img src="https://mintlify.s3.us-west-1.amazonaws.com/mcp/images/claude-desktop-mcp-hammer-icon.svg" width="80" alt="MCP Docs"><br>
          <b>MCP Documentation</b>
        </a>
      </td>
    </tr>
  </table>
</div>

## 📄 License

<div align="center">
  
  This project is licensed under the [MIT License](LICENSE).
  
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  
</div>
