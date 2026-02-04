# Vivian Core Package

This repository represents the core package of the Vivian Framework. This package can be included in Unity projects using the Package Manager. It contains all classes required to run virtual prototypes. It also contains a documentation for how to configure virtual prototypes.

# What does a virtual prototype look like?
A virtual prototype in Vivian is a 3D model accompanied with configuration files. Vivian reads the configuration files to make the static 3D model interactive.

To allow Vivian to interpret the model file and the configuration files correctly, the files need to adhere to a certain folder structure on the disk. This structure looks like the following:

+ *Prototype folder*: usually named after the prototype
  + *3D Model file*: can be a Unity Prefab (recommended) or a plain 3D model file, such as an FBX or Blender file.
  + *FunctionalSpecification*: contains the configuration files
    + *InteractionElements.json*: defines which elements of the 3D model are interactive such as buttons, touch areas, etc.
    + *VisualizationElements.json*: defines which elements of the 3D model visualize something, such as a light, a screen, or an audio source
    + *VisualizationArrays.json*: allow for combining multiple visualization elements to a single one, used only rarely
    + *States.json*: defines the states in which a prototype can be (e.g., *off*, *waiting*, *heating*) and what the visualization elements are supposed to visualize in a certain state
    + *Transitions.json*: defines under which circumstances (interaction with an interaction element and guards) a prototype changes from one state to another
  + *Screens* (optional, contains images to be displayed on virtual screens of a prototype)
  + *Materials* (optional, contains materials used by the 3D model)

The details for the contents of the different files in the *FunctionalSpecification* folder are described in the Docs folder of this repository. All files are written in JSON format and are, therefore, human readable and editable.

### 🧩 1. Interaction Elements

Defines all elements that allow user interaction within the virtual prototype (e.g., buttons, sliders, knobs).

📄 [Read the documentation ›](./Docs/InteractionElementsDocu.md)

### 🖼️ 2. Visualization Elements

Specifies visual output elements such as lights, screens, animations, and effects.

📄 [Read the documentation ›](./Docs/VisualizationElementsDocu.md)

### 🧠 3. States

Describes the different states of the virtual prototype and the corresponding configuration of its components.

📄 [Read the documentation ›](./Docs/StatesDocu.md)

### 🔁 4. Transitions

Defines how the prototype moves between states, triggered by events or timeouts, optionally with guard conditions.

📄 [Read the documentation ›](./Docs/TransitionsDocu.md)


