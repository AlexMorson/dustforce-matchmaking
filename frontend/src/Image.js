import "./Image.css";

function Image({ level }) {
  return (
    <a href={level.play}>
      <div className={"image"}>
        <img alt={level.name} src={level.image} />
        <span>{level.name}</span>
      </div>
    </a>
  );
}

export default Image;
