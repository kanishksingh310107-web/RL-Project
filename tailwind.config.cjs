module.exports = {
  content: ['./static/**/*.{html,js}'],
  safelist: [{pattern: /^(bg|text|border)-(slate|gray|indigo|violet|purple|blue|emerald|green|amber|orange|rose|red)-(50|100|200|300|400|500|600|700|800|900)$/}],
  theme: {extend: {}},
  plugins: []
};
