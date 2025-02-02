### 🚀 **VectorMorph - SVG to Animated WebP/GIF Converter** 🎨✨

VectorMorph is a powerful web application that transforms SVG files into **animated WebP or GIF** files. It allows smooth animations using **frame blending and fade transitions**, ensuring **high-quality and visually cohesive outputs**. 

---

## 🎯 **Features**
✅ Convert **multiple SVG files** into animated WebP or GIF  
✅ **Smart animation** options for a smooth look:
   - 🌀 **Frame blending** (merges frames for fluid transitions)  
   - 🌫 **Fade transitions** (gradual visibility shifts)  
✅ **Customizable settings**:
   - 🕒 Frame duration (in milliseconds)  
   - 🎨 Background color (with transparency support)  
   - ⚖ Blend amount & fade steps  
✅ **Real-time progress tracking** (via WebSockets)  
✅ **Maintains frame order**: The uploaded files are processed **in the exact order** to ensure a **smooth, cohesive animation**.  

---

## 🔧 **Installation**

1️⃣ **Clone the repository**  
```bash
git clone https://github.com/yourusername/vectormorph.git
cd vectormorph
```

2️⃣ **Create and activate a virtual environment**  
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3️⃣ **Install dependencies**  
```bash
pip install -r requirements.txt
```

---

## 🚀 **Usage**

1️⃣ **Start the server**  
```bash
python app.py
```

2️⃣ **Open in a browser**  
```
http://localhost:5001
```

3️⃣ **Upload your SVG files** and configure the conversion settings:
   - 📂 Select **multiple SVG files**  
   - ⏳ Set frame duration  
   - 🌀 Choose smart animation effects (optional)  
   - 🎨 Select background color  
   - 🔄 Choose output format (WebP or GIF)  

4️⃣ **Click "Convert"** and wait for the process to complete.  
5️⃣ **Download your converted animation** 🎉  

---

## 📂 **Project Structure**
```
/vectormorph
│── /static              # Static assets (CSS, JS, images)
│   ├── /assets          # Background images
│   │   └── frames.svg   # Background for the UI
│   ├── /converted       # Stores converted output files
│── /templates           # HTML templates
│   ├── base.html        # Base template for UI
│   ├── index.html       # Upload and conversion page
│   ├── result.html      # Display converted results
│── /logs                # Application logs
│   └── app.log          # Log file for tracking errors
│── /utils               # Utility functions
│   ├── image_processing.py  # Image processing (blending, fading)
│   ├── file_utils.py        # File handling utilities
│── app.py              # Main Flask application
│── config.py           # Configuration settings
│── requirements.txt    # Python dependencies
│── README.md           # Documentation
```

---

## 🔌 **Technology Stack**
- 🐍 **Python 3.8+**  
- 🌐 **Flask** (Web Framework)  
- 🔥 **Flask-SocketIO** (Real-time progress updates)  
- 🖼 **Pillow** (Image Processing)  
- 🎨 **CairoSVG** (SVG Rendering)  
- 🔢 **NumPy** (Numerical operations)  

---

## ⚠ **Error Handling & Logging**
📝 The application logs events in **`logs/app.log`**, capturing errors like:  
```
2025-02-01 19:09:56,869 - ERROR - Conversion error: name 'url_for' is not defined
```
This helps debug issues effectively.

---

## 🛠 **Customization**
### 🔹 **Background Image**
The background image used in the app UI is stored at:  
```
vectormorph/static/assets/frames.svg
```
You can **replace it** with any custom design.

### 🔹 **File Order & Animation Quality**
- The **order of uploaded files** is **preserved** in conversion, ensuring a **seamless animation**.  
- To enhance animation smoothness, **upload sequential frames in proper order**.  

---

## 📜 **License**
This project is licensed under the **MIT License** - see the LICENSE file for details.

---

## 👨‍💻 **Contributing**
1️⃣ **Fork the repository**  
2️⃣ **Create your feature branch**  
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3️⃣ **Commit your changes**  
   ```bash
   git commit -m 'Add AmazingFeature'
   ```
4️⃣ **Push to the branch**  
   ```bash
   git push origin feature/AmazingFeature
   ```
5️⃣ **Open a Pull Request**  

---

## 🎉 **Acknowledgments**
🚀 Huge thanks to the amazing libraries powering this project:
- **[CairoSVG](https://cairosvg.org/)** for SVG to PNG conversion  
- **[Flask](https://flask.palletsprojects.com/)** for the backend framework  
- **[Socket.IO](https://socket.io/)** for real-time progress updates  

---

💡 **Enjoy using VectorMorph!** If you have feature suggestions, open an issue! 🚀