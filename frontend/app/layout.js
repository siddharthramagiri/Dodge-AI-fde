import "./globals.css";

export const metadata = {
  title: "Dodge AI - Order to Cash Graph",
  description: "SAP Order to Cash context graph with AI query chat"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
