export const metadata = {
  title: "AI Novel Translation",
  description: "AI-assisted novel translation workflow",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
