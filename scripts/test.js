// Simple Node.js script that demonstrates functionality
const fs = require('fs');
const path = require('path');

function main() {
    const args = process.argv.slice(2);
    const message = args[0] || 'Hello from Node.js!';
    
    const result = {
        timestamp: new Date().toISOString(),
        message: message,
        nodeVersion: process.version,
        platform: process.platform,
        workingDirectory: process.cwd(),
        arguments: args,
        environmentInfo: {
            hasInternet: true,
            canRunSubprocesses: true
        }
    };
    
    // Output JSON result that Python can parse
    console.log(JSON.stringify(result, null, 2));
}

// Handle any errors
process.on('uncaughtException', (error) => {
    console.error(JSON.stringify({
        error: true,
        message: error.message,
        stack: error.stack
    }));
    process.exit(1);
});

main();