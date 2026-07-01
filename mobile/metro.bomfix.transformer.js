const upstream = require("metro-react-native-babel-transformer");

function stripBOM(src = "") {
  return String(src)
    .replace(/^\uFEFF/, "")                         // BOM
    .replace(/^(?:\u00EF\u00BB\u00BF|"");    
}

module.exports = {
  transform(props) {
    const { src, filename, options } = props;
    const clean = stripBOM(src);
    return upstream.transform({ src: clean, filename, options });
  },
};








