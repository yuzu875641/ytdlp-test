const path = require('path');

module.exports = {
    entry: './src/index.js',
    output: {
        filename: 'webpack.js',
        path: path.resolve(__dirname, '../static/scripts/dist'),
    },
    mode: 'development',
};