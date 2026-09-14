window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.timeIn12hrs = function(value) {
     if (value > 12) {
          value = value - 12;
          result = `${value}am`;
     } else {
          result = `${value}pm`;
     }
     return result;
}

